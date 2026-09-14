import json
import zlib
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from api.db.cassandra import get_cassandra_session
from api.db.redis import get_redis
from api.models.cassandra import SensorReading


router = APIRouter(prefix="/sensors", tags=["Sensors"])


def _dashboard_shard(sensor_id: str) -> int:
    return zlib.crc32(sensor_id.encode("utf-8")) % 16


def _insert_readings(readings: list[SensorReading]):
    session = get_cassandra_session()

    sensor_query = session.prepare(
        """
        INSERT INTO sensor_readings
        (
            sensor_id,
            reading_time,
            metric_type,
            value,
            unit,
            quality_flag
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """
    )

    dashboard_query = session.prepare(
        """
        INSERT INTO dashboard_readings
        (
            bucket_minute,
            shard,
            reading_time,
            sensor_id,
            metric_type,
            value,
            unit,
            quality_flag
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
    )

    for reading in readings:
        session.execute(
            sensor_query,
            (
                reading.sensor_id,
                reading.reading_time,
                reading.metric_type,
                reading.value,
                reading.unit,
                reading.quality_flag,
            ),
        )

        bucket_minute = reading.reading_time.replace(
            second=0,
            microsecond=0,
        )

        session.execute(
            dashboard_query,
            (
                bucket_minute,
                _dashboard_shard(reading.sensor_id),
                reading.reading_time,
                reading.sensor_id,
                reading.metric_type,
                reading.value,
                reading.unit,
                reading.quality_flag,
            ),
        )


@router.post("/readings")
async def create_readings(
    reading: SensorReading | list[SensorReading],
):
    readings = reading if isinstance(reading, list) else [reading]

    if not readings:
        raise HTTPException(
            status_code=400,
            detail="At least one sensor reading is required",
        )

    await run_in_threadpool(_insert_readings, readings)

    redis_client = await get_redis()

    for sensor_id in {item.sensor_id for item in readings}:
        await redis_client.delete(f"sensor_summary:{sensor_id}")

    return {
        "message": "Sensor readings created successfully",
        "inserted": len(readings),
    }


def _fetch_readings(
    sensor_id: str,
    limit: int,
    from_time: datetime | None,
):
    session = get_cassandra_session()

    if from_time is not None:
        query = session.prepare(
            f"""
            SELECT sensor_id,
                   reading_time,
                   metric_type,
                   value,
                   unit,
                   quality_flag
            FROM sensor_readings
            WHERE sensor_id = ?
              AND reading_time >= ?
            LIMIT {limit}
            """
        )

        rows = session.execute(
            query,
            (sensor_id, from_time),
        )

    else:
        query = session.prepare(
            f"""
            SELECT sensor_id,
                   reading_time,
                   metric_type,
                   value,
                   unit,
                   quality_flag
            FROM sensor_readings
            WHERE sensor_id = ?
            LIMIT {limit}
            """
        )

        rows = session.execute(
            query,
            (sensor_id,),
        )

    return [dict(row._asdict()) for row in rows]


@router.get("/{sensor_id}/readings")
async def get_readings(
    sensor_id: str,
    limit: int = Query(100, ge=1, le=1000),
    from_time: datetime | None = None,
):
    return await run_in_threadpool(
        _fetch_readings,
        sensor_id,
        limit,
        from_time,
    )


def _build_summary(sensor_id: str):
    session = get_cassandra_session()

    latest_query = session.prepare(
        """
        SELECT sensor_id,
               reading_time,
               metric_type,
               value,
               unit,
               quality_flag
        FROM sensor_readings
        WHERE sensor_id = ?
        LIMIT 1
        """
    )

    latest = session.execute(
        latest_query,
        (sensor_id,),
    ).one()

    if latest is None:
        return None

    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)

    stats_query = session.prepare(
        """
        SELECT reading_time,
               metric_type,
               value,
               unit,
               quality_flag
        FROM sensor_readings
        WHERE sensor_id = ?
          AND reading_time >= ?
        """
    )

    rows = list(
        session.execute(
            stats_query,
            (sensor_id, one_hour_ago),
        )
    )

    metrics = {}

    for row in rows:
        metrics.setdefault(row.metric_type, []).append(row.value)

    stats = {}

    for metric_type, values in metrics.items():
        stats[metric_type] = {
            "count": len(values),
            "average": sum(values) / len(values),
            "minimum": min(values),
            "maximum": max(values),
        }

    return {
        "sensor_id": sensor_id,
        "latest": {
            "reading_time": latest.reading_time,
            "metric_type": latest.metric_type,
            "value": latest.value,
            "unit": latest.unit,
            "quality_flag": latest.quality_flag,
        },
        "last_hour": stats,
    }


@router.get("/{sensor_id}/summary")
async def get_summary(sensor_id: str):
    redis_client = await get_redis()

    cache_key = f"sensor_summary:{sensor_id}"

    cached = await redis_client.get(cache_key)

    if cached:
        return json.loads(cached)

    summary = await run_in_threadpool(
        _build_summary,
        sensor_id,
    )

    if summary is None:
        raise HTTPException(
            status_code=404,
            detail="No readings found for this sensor",
        )

    await redis_client.set(
        cache_key,
        json.dumps(summary, default=str),
        ex=30,
    )

    return summary
