from fastapi import APIRouter
from api.models.alerts import AlertPublish
from api.db.redis import get_redis
from datetime import datetime


router = APIRouter(prefix="/alerts", tags=["Alerts"])


@router.get("/active")
async def get_active_alerts():
    redis_client = await get_redis()

    alerts = await redis_client.lrange("active_alerts", 0, -1)

    return {
        "alerts": alerts,
        "count": len(alerts)
    }


@router.post("/publish")
async def publish_alert(alert: AlertPublish):
    redis_client = await get_redis()

    message = {
        "severity": alert.severity,
        "message": alert.message,
        "node_id": alert.node_id,
        "created_at": datetime.utcnow().isoformat()
    }

    import json

    message_json = json.dumps(message)

    await redis_client.publish(
        "grid_alerts",
        message_json
    )

    await redis_client.lpush(
        "active_alerts",
        message_json
    )

    return {
        "message": "Alert published successfully",
        "alert": message
    }
