"""Replay durable fault alerts into the graph after temporary outages."""

import asyncio
import json
import logging

from redis.exceptions import ResponseError

from api.db.neo4j import get_neo4j_driver
from api.db.redis import get_redis


STREAM = "fault_alert_events"
GROUP = "neo4j_fault_updates"
CONSUMER = "gridsense_api"
logger = logging.getLogger(__name__)


async def prepare_fault_stream():
    client = await get_redis()
    try:
        await client.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
    except ResponseError as error:
        if "BUSYGROUP" not in str(error):
            raise


async def _apply_fault(event_id: str, payload: dict) -> bool:
    node_id = payload.get("node_id")
    if not node_id:
        return True

    driver = await get_neo4j_driver()
    async with driver.session(database="neo4j") as session:
        result = await session.run(
            """MATCH (n)
            WHERE n.node_id = $node_id OR n.gsp_id = $node_id
               OR n.substation_id = $node_id OR n.asset_id = $node_id
               OR n.meter_id = $node_id
            SET n.fault_alert_active = true,
                n.last_fault_event_id = $event_id,
                n.last_fault_at = datetime($created_at)
            RETURN count(n) AS updated""",
            node_id=node_id,
            event_id=event_id,
            created_at=payload["created_at"],
        )
        record = await result.single()
        return record["updated"] > 0


async def run_fault_worker():
    client = await get_redis()
    while True:
        try:
            # Revisit unacknowledged entries after an API restart.
            messages = await client.xreadgroup(
                GROUP, CONSUMER, {STREAM: "0"}, count=10
            )

            has_entries = any(entries for _, entries in messages)

            if not has_entries:
               messages = await client.xreadgroup(
                   GROUP,
                   CONSUMER,
                   {STREAM: ">"},
                   count=10,
                   block=1000,
               )


            for _, entries in messages:
                for event_id, fields in entries:
                    payload = json.loads(fields["payload"])
                    try:
                        applied = await _apply_fault(event_id, payload)
                    except Exception:
                        logger.exception("Neo4j unavailable; fault %s remains queued", event_id)
                        await asyncio.sleep(2)
                        break
                    if not applied:
                        await client.xadd(
                            "fault_alerts_dead_letter",
                            {"event_id": event_id, "payload": fields["payload"]},
                        )
                        logger.error("Unknown graph node for fault %s", event_id)
                    await client.xack(STREAM, GROUP, event_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Fault worker interrupted; retrying")
            await asyncio.sleep(2)
