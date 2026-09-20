"""Integration checks: BILLING_TEST_DSN must point to a disposable PostgreSQL database.
Run: python -m unittest discover -s tests -p 'test_billing.py' -v
Each test uses and removes its own isolated schema.
"""
import ast
import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
import os
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
import uuid

import asyncpg
from fastapi import FastAPI, HTTPException
from pydantic import ValidationError

import api.db.postgres as database
from api.models.postgres import InvoiceCreate
from api.routers.billing import create_invoice, get_billing_account, router

ROOT = Path(__file__).resolve().parents[1]
DSN = os.getenv('BILLING_TEST_DSN')


@unittest.skipUnless(DSN, 'Set BILLING_TEST_DSN to a disposable PostgreSQL database')
class BillingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.schema = 'billing_test_' + uuid.uuid4().hex
        self.admin = await asyncpg.connect(DSN)
        await self.admin.execute(f'CREATE SCHEMA {self.schema}')
        self.pool = await asyncpg.create_pool(DSN, min_size=1, max_size=10,
                                             server_settings={'search_path': self.schema})
        database.pool = self.pool
        async with self.pool.acquire() as conn:
            await conn.execute((ROOT / 'postgres/init.sql').read_text())
            await conn.execute("INSERT INTO consumer_accounts (premise_id,customer_name,balance) VALUES ('P','Customer',0),('LEGACY','Old',7)")
            await conn.execute("INSERT INTO invoices (premise_id,amount,due_date) VALUES ('LEGACY',12.34,now()),('LEGACY',-10,now())")
            await database.apply_billing_schema(conn)

    async def asyncTearDown(self):
        database.pool = None
        await self.pool.close()
        await self.admin.execute(f'DROP SCHEMA {self.schema} CASCADE')
        await self.admin.close()

    def invoice(self, **changes):
        data = dict(premise_id='P', amount='12.34', billing_period='2026-09-01',
                    due_date='2026-10-15T00:00:00Z', description='Monthly charge')
        data.update(changes)
        return InvoiceCreate(**data)

    async def test_exact_money_and_idempotent_retry(self):
        first = await create_invoice(self.invoice(amount='0.10'))
        again = await create_invoice(self.invoice(amount='0.10'))
        await create_invoice(self.invoice(amount='0.20', billing_period='2026-10-01'))
        self.assertTrue(first['created']); self.assertFalse(again['created'])
        self.assertEqual(first['invoice'], again['invoice'])
        self.assertEqual((await get_billing_account('P')).balance, Decimal('0.30'))

    async def test_concurrent_identical_requests_charge_once(self):
        results = await asyncio.gather(*(create_invoice(self.invoice()) for _ in range(8)))
        self.assertEqual(sum(r['created'] for r in results), 1)
        self.assertEqual(len({r['invoice']['invoice_id'] for r in results}), 1)
        self.assertEqual((await get_billing_account('P')).balance, Decimal('12.34'))

    async def test_concurrent_conflicts_and_different_months(self):
        results = await asyncio.gather(*(create_invoice(self.invoice(amount=str(i))) for i in range(1,9)), return_exceptions=True)
        successes = [r for r in results if isinstance(r,dict)]
        self.assertEqual(len(successes),1)
        self.assertTrue(all(isinstance(r,dict) or isinstance(r,HTTPException) and r.status_code==409 for r in results))
        await asyncio.gather(*(create_invoice(self.invoice(amount='0.01',billing_period=date(2027,i,1))) for i in range(1,9)))
        self.assertEqual((await get_billing_account('P')).balance, successes[0]['invoice']['amount'] + Decimal('0.08'))

    async def test_overflow_rolls_back_invoice(self):
        await self.pool.execute("UPDATE consumer_accounts SET balance=9999999999.99 WHERE premise_id='P'")
        with self.assertRaises(HTTPException) as error:
            await create_invoice(self.invoice())
        self.assertEqual(error.exception.status_code,409)
        self.assertEqual(await self.pool.fetchval("SELECT count(*) FROM invoices WHERE premise_id='P'"),0)
        self.assertEqual((await get_billing_account('P')).balance,Decimal('9999999999.99'))

    async def test_database_failure_rolls_back_invoice(self):
        await self.pool.execute("""CREATE FUNCTION reject_balance() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION 'test failure'; END $$;
            CREATE TRIGGER reject_balance BEFORE UPDATE ON consumer_accounts
            FOR EACH ROW EXECUTE FUNCTION reject_balance();""")
        with self.assertRaises(asyncpg.RaiseError):
            await create_invoice(self.invoice())
        self.assertEqual(await self.pool.fetchval("SELECT count(*) FROM invoices WHERE premise_id='P'"),0)
        self.assertEqual((await get_billing_account('P')).balance,Decimal('0.00'))

    async def test_legacy_migration_preserves_data_and_blocks_unsafe_charge(self):
        async with self.pool.acquire() as conn:
            await database.apply_billing_schema(conn)
        account = await get_billing_account('LEGACY')
        self.assertTrue(account.requires_reconciliation)
        self.assertEqual(account.balance,Decimal('7.00'))
        self.assertEqual(await self.pool.fetchval("SELECT count(*) FROM invoices WHERE premise_id='LEGACY' AND billing_period IS NULL"),2)
        with self.assertRaises(HTTPException) as error:
            await create_invoice(self.invoice(premise_id='LEGACY'))
        self.assertEqual(error.exception.status_code,409)

    async def test_input_validation_and_missing_account(self):
        for amount in ['-1','0','1.001','10000000000','NaN','Infinity',True]:
            with self.subTest(amount=amount), self.assertRaises(ValidationError):
                self.invoice(amount=amount)
        for changes in [dict(billing_period='2026-09-02'), dict(billing_period=None), dict(due_date='2026-10-15T00:00:00')]:
            with self.assertRaises(ValidationError): self.invoice(**changes)
        with self.assertRaises(HTTPException) as error:
            await create_invoice(self.invoice(premise_id='MISSING'))
        self.assertEqual(error.exception.status_code,404)

    async def test_database_constraints(self):
        for amount,period in [(Decimal('-1'),date(2026,1,1)),(Decimal('NaN'),date(2026,1,1)),(Decimal('1'),None),(Decimal('1'),date(2026,1,2))]:
            with self.assertRaises(asyncpg.CheckViolationError):
                await self.pool.execute("INSERT INTO invoices (premise_id,amount,billing_period,due_date) VALUES ('P',$1,$2,now())",amount,period)
        await create_invoice(self.invoice())
        with self.assertRaises(asyncpg.UniqueViolationError):
            await self.pool.execute("INSERT INTO invoices (premise_id,amount,billing_period,due_date) VALUES ('P',1,'2026-09-01',now())")

    async def test_http_validation_retries_and_exact_money_serialization(self):
        app = FastAPI()
        app.include_router(router)

        async def request(payload):
            messages = []
            async def receive():
                return {"type": "http.request", "body": json.dumps(payload).encode(), "more_body": False}
            async def send(message):
                messages.append(message)
            await app({"type": "http", "asgi": {"version": "3.0"},
                       "http_version": "1.1", "method": "POST", "scheme": "http",
                       "path": "/billing/invoice", "raw_path": b"/billing/invoice",
                       "query_string": b"", "headers": [(b"content-type",b"application/json")],
                       "client": ("127.0.0.1",1), "server": ("test",80)}, receive, send)
            status = next(m['status'] for m in messages if m['type']=='http.response.start')
            body = json.loads(b''.join(m.get('body',b'') for m in messages if m['type']=='http.response.body'))
            return status, body

        payload = self.invoice().model_dump(mode='json')
        status, first = await request(payload)
        self.assertEqual(status,200)
        self.assertEqual(first['invoice']['amount'],'12.34')
        status, retry = await request(payload)
        self.assertEqual(status,200); self.assertFalse(retry['created'])
        for key,value in [('amount','13.00'),('description','Changed'),('due_date','2026-11-15T00:00:00Z')]:
            status, _ = await request({**payload,key:value})
            self.assertEqual(status,409)
        del payload['billing_period']
        status, _ = await request(payload)
        self.assertEqual(status,422)

    async def test_billing_seed_is_repeatable_without_resetting_balance(self):
        source = ROOT / 'scripts/seed.py'
        tree = ast.parse(source.read_text())
        function = next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='seed_postgres')
        async def connect(**kwargs):
            return await asyncpg.connect(DSN,server_settings={'search_path':self.schema})
        env = dict(__file__=str(source), asyncpg=SimpleNamespace(connect=connect), Path=Path,
                   Decimal=Decimal,date=date,datetime=datetime,timezone=timezone,
                   POSTGRES_HOST='',POSTGRES_PORT=5432,POSTGRES_USER='',POSTGRES_PASSWORD='',POSTGRES_DB='')
        exec(compile(ast.Module(body=[function],type_ignores=[]),str(source),'exec'),env)
        await env['seed_postgres']()
        before = (await get_billing_account('PREM001')).balance
        self.assertEqual(before,Decimal('41.00'))
        await create_invoice(self.invoice(premise_id='PREM001',billing_period='2026-11-01'))
        await env['seed_postgres']()
        self.assertEqual((await get_billing_account('PREM001')).balance,before+Decimal('12.34'))
        self.assertEqual(await self.pool.fetchval("SELECT count(*) FROM invoices WHERE premise_id='PREM001'"),2)


if __name__ == '__main__':
    unittest.main()
