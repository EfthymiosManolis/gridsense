"""Run only against an EMPTY disposable Neo4j database.
Set RESTORE_TEST_ENABLED=1 and NEO4J_URI/NEO4J_USER/NEO4J_PASSWORD.
These integration tests clear the graph between cases.
"""
import os
from pathlib import Path
import unittest
from fastapi import HTTPException
from neo4j import AsyncGraphDatabase

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.getenv('RESTORE_TEST_ENABLED') == '1', 'Requires disposable Neo4j')
class RestoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from api.routers import grid
        from api.db import neo4j
        await neo4j.driver.close()
        self.driver = AsyncGraphDatabase.driver(os.environ['NEO4J_URI'],
                     auth=(os.environ['NEO4J_USER'], os.environ['NEO4J_PASSWORD']))
        neo4j.driver = self.driver
        self.grid = grid
        await self.query('MATCH (n) DETACH DELETE n')
        for statement in (ROOT/'neo4j/import/seed.cypher').read_text().split(';'):
            if statement.strip(): await self.query(statement)
        self.ties = (ROOT/'neo4j/import/restore_ties.cypher').read_text()
        await self.query(self.ties)

    async def asyncTearDown(self):
        await self.query('MATCH (n) DETACH DELETE n')
        await self.driver.close()

    async def query(self, query):
        async with self.driver.session(database='neo4j') as session:
            result = await session.run(query)
            return await result.data()

    async def test_fault_bypassed_with_explicit_switch_action(self):
        await self.query("MATCH (n:Transformer {asset_id:'TR1'}) SET n.fault_alert_active=true")
        result = await self.grid.restore_paths('MTR1')
        self.assertEqual(result['restore_paths'],[['GSP001','SUB2','TR5','MTR1']])
        self.assertTrue(result['requires_operator_validation'])
        switch = result['candidates'][0]['required_switches'][0]
        self.assertEqual((switch['from_node'],switch['to_node'],switch['action']),('TR5','MTR1','close'))
        await self.query("MATCH (n:Transformer {asset_id:'TR1'}) SET n.fault_alert_active=false")
        self.assertEqual((await self.grid.restore_paths('MTR1'))['restore_paths'],result['restore_paths'])

    async def test_faulted_target_source_backup_and_unavailable_nodes(self):
        for predicate,property_name in [("asset_id:'TR5'",'fault_alert_active'),("meter_id:'MTR1'",'fault_alert_active'),("gsp_id:'GSP001'",'fault_alert_active'),("substation_id:'SUB2'",'available')]:
            value = 'false' if property_name=='available' else 'true'
            await self.query(f'MATCH (n {{{predicate}}}) SET n.{property_name}={value}')
            self.assertEqual((await self.grid.restore_paths('MTR1'))['restore_paths'],[])
            await self.query(f'MATCH (n {{{predicate}}}) REMOVE n.{property_name}')

    async def test_unusable_edges_and_closed_ties_not_proposed(self):
        for property_name,value in [('available','false'),('fault_alert_active','true'),('switchable','false'),('is_open','false')]:
            await self.query(f"MATCH ()-[r {{tie_id:'BACKUP_TR5_MTR1'}}]->() SET r.{property_name}={value}")
            self.assertEqual((await self.grid.restore_paths('MTR1'))['restore_paths'],[])
            await self.query("MATCH ()-[r {tie_id:'BACKUP_TR5_MTR1'}]->() SET r.available=true,r.fault_alert_active=false,r.switchable=true,r.is_open=true")

    async def test_unknown_and_ambiguous_ids(self):
        with self.assertRaises(HTTPException) as error:
            await self.grid.restore_paths('MISSING')
        self.assertEqual(error.exception.status_code,404)
        await self.query("CREATE (:Transformer {node_id:'MTR1'})")
        with self.assertRaises(HTTPException) as error:
            await self.grid.restore_paths('MTR1')
        self.assertEqual(error.exception.status_code,409)

    async def test_fault_impact_and_repeatable_tie_seed(self):
        before = await self.grid.fault_impact('TR5')
        self.assertEqual(before.total_affected,5)
        self.assertNotIn('MTR1',[n.node_id for n in before.affected_nodes])
        await self.query("MATCH ()-[r {tie_id:'BACKUP_TR5_MTR1'}]->() SET r.is_open=false")
        await self.query(self.ties)
        count = await self.query("MATCH ()-[r:CONNECTS_TO]->() WHERE r.tie_id IS NOT NULL RETURN count(r) AS count")
        self.assertEqual(count[0]['count'],5)
        after = await self.grid.fault_impact('TR5')
        self.assertEqual(after.total_affected,6)
        self.assertIn('MTR1',[n.node_id for n in after.affected_nodes])
        self.assertEqual((await self.grid.restore_paths('MTR21'))['restore_paths'],[])


if __name__=='__main__': unittest.main()
