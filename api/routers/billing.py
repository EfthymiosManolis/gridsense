from fastapi import APIRouter, HTTPException
from api.models.postgres import BillingAccount, InvoiceCreate, InvoiceResponse
from api.db.postgres import get_postgres_pool


router = APIRouter(prefix="/billing", tags=["Billing"])


@router.get("/account/{premise_id}", response_model=BillingAccount)
async def get_billing_account(premise_id: str):
    pool = get_postgres_pool()
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            """SELECT a.premise_id, a.customer_name, a.address,
                      a.account_status, a.balance,
                      EXISTS (SELECT 1 FROM invoices i
                              WHERE i.premise_id = a.premise_id
                                AND i.billing_period IS NULL) AS requires_reconciliation
               FROM consumer_accounts a WHERE a.premise_id = $1""",
            premise_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="Billing account not found")
    return BillingAccount(**dict(row))


@router.post("/invoice", response_model=InvoiceResponse)
async def create_invoice(invoice: InvoiceCreate):
    pool = get_postgres_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            # Serialize invoices for one account, including requests for different months.
            account = await connection.fetchrow(
                "SELECT balance FROM consumer_accounts WHERE premise_id = $1 FOR UPDATE",
                invoice.premise_id,
            )
            if account is None:
                raise HTTPException(status_code=404, detail="Billing account not found")

            row = await connection.fetchrow(
                """SELECT invoice_id, premise_id, amount, billing_period, due_date, description
                   FROM invoices WHERE premise_id = $1 AND billing_period = $2""",
                invoice.premise_id, invoice.billing_period,
            )
            if row is not None:
                if (row['amount'], row['due_date'], row['description']) != (
                    invoice.amount, invoice.due_date, invoice.description
                ):
                    raise HTTPException(status_code=409, detail="An invoice with different details already exists for this billing period")
                return {"message": "Invoice already exists", "created": False,
                        "invoice": dict(row)}

            legacy = await connection.fetchval(
                """SELECT EXISTS (SELECT 1 FROM invoices
                   WHERE premise_id = $1 AND billing_period IS NULL)""",
                invoice.premise_id,
            )
            if legacy:
                raise HTTPException(status_code=409, detail="Historical invoices have unknown billing periods. Reconcile their periods and account balance before issuing a new invoice.")

            row = await connection.fetchrow(
                """INSERT INTO invoices
                       (premise_id, amount, billing_period, due_date, description)
                   VALUES ($1, $2, $3, $4, $5)
                   RETURNING invoice_id, premise_id, amount, billing_period, due_date, description""",
                invoice.premise_id, invoice.amount, invoice.billing_period,
                invoice.due_date, invoice.description,
            )
            balance = await connection.fetchval(
                """UPDATE consumer_accounts SET balance = balance + $2
                   WHERE premise_id = $1 AND balance + $2 <= 9999999999.99
                   RETURNING balance""",
                invoice.premise_id, invoice.amount,
            )
            if balance is None:
                # Raising inside the transaction also rolls back the invoice insertion.
                raise HTTPException(status_code=409, detail="Invoice would exceed the account balance limit")

    return {"message": "Invoice created successfully", "created": True,
            "invoice": dict(row)}
