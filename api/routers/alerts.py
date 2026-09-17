from fastapi import APIRouter
from api.models.alerts import AlertPublish
from api.db.redis import get_redis
from datetime import datetime, timezone
import json


router = APIRouter(prefix="/alerts", tags=["Alerts"])


@router.get("/active")
async def get_active_alerts():
    redis_client = await get_redis()

    alert_strings = await redis_client.lrange(
        "active_alerts",
        0,
        -1,
    )

    alerts = [
        json.loads(alert)
        for alert in alert_strings
    ]

    return {
        "alerts": alerts,
        "count": len(alerts),
    }

@router.post("/publish")
async def publish_alert(alert: AlertPublish):
    redis_client = await get_redis()

    message = {
        "severity": alert.severity,
        "message": alert.message,
        "node_id": alert.node_id,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    message_json = json.dumps(message)

    async with redis_client.pipeline(transaction=True) as pipe:
        pipe.xadd("fault_alert_events", {"payload": message_json})
        pipe.lpush("active_alerts", message_json)
        pipe.ltrim("active_alerts", 0, 999)
        pipe.publish("grid_alerts", message_json)
        event_id = (await pipe.execute())[0]
    message["event_id"] = event_id

    return {
        "message": "Alert published successfully",
        "alert": message
    }
