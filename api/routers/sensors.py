import json
import zlib
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, Response
from starlette.concurrency import run_in_threadpool

from api.db.cassandra import get_cassandra_session
from api.db.redis import get_redis
from api.models.cassandra import SensorReading


router = APIRouter(prefix="/sensors", tags=["Sensors"])
RETENTION_DAYS = 90
SHARDS = 16


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _days_newest_first(start: date, end: date):
    day = end
    while day >= start:
        yield day
        day -= timedelta(days=1)


def _dashboard_shard(sensor_id: str) -> int:
    return zlib.crc32(sensor_id.encode("utf-8")) % SHARDS


def _insert_readings(readings: list[SensorReading]):
    session = get_cassandra_session()

    sensor_query = session.prepare(
        """
        INSERT INTO sensor_readings
        (
            sensor_id,
            date_bucket,
            reading_time,
            region_id,
            metric_type,
            value,
            unit,
            quality_flag
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
    )

    regional_query = session.prepare(
        """
        INSERT INTO regional_readings
        (
            region_id,
            date_bucket,
            shard,
            reading_time,
            sensor_id,
            metric_type,
            value,
            unit,
            quality_flag
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
    )

    for reading in readings:
        reading_time = _utc(reading.reading_time)
        session.execute(
            sensor_query,
            (
                reading.sensor_id,
                reading_time.date(),
                reading_time,
                reading.region_id,
                reading.metric_type,
                reading.value,
                reading.unit,
                reading.quality_flag,
            ),
        )

        session.execute(
            regional_query,
            (
                reading.region_id,
                reading_time.date(),
                _dashboard_shard(reading.sensor_id),
                reading_time,
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
    await redis_client.sadd("sensor_regions", *{item.region_id for item in readings})

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
    now = datetime.now(timezone.utc)
    earliest = now - timedelta(days=RETENTION_DAYS)
    start = max(_utc(from_time), earliest) if from_time else earliest
    if start > now:
        return []
    query = session.prepare(
        """SELECT sensor_id, region_id, reading_time, metric_type, value, unit, quality_flag
        FROM sensor_readings
        WHERE sensor_id = ? AND date_bucket = ? AND reading_time >= ?
        LIMIT ?"""
    )
    result = []
    for bucket in _days_newest_first(start.date(), now.date()):
        rows = session.execute(query, (sensor_id, bucket, start, limit - len(result)))
        result.extend(dict(row._asdict()) for row in rows)
        if len(result) >= limit:
            break
    return result


def _fetch_network_recent(end: datetime, limit: int, offset: int, regions: list[str]):
    session = get_cassandra_session()
    start = end - timedelta(seconds=60)
    fetch_size = offset + limit + 1
    query = session.prepare(
        """SELECT region_id, reading_time, sensor_id, metric_type, value, unit, quality_flag
        FROM regional_readings
        WHERE region_id = ? AND date_bucket = ? AND shard = ?
          AND reading_time > ? AND reading_time <= ?
        LIMIT ?"""
    )
    buckets = {start.date(), end.date()}
    rows = []
    for region_id in regions:
        for bucket in sorted(buckets):
            for shard in range(SHARDS):
                rows.extend(
                    dict(row._asdict())
                    for row in session.execute(
                        query, (region_id, bucket, shard, start, end, fetch_size)
                    )
                )
    rows.sort(key=lambda row: (row["reading_time"], row["sensor_id"],
                               row["metric_type"]), reverse=True)
    page = rows[offset:offset + limit]
    return {
        "as_of": end,
        "window_start": start,
        "offset": offset,
        "limit": limit,
        "returned": len(page),
        "has_more": len(rows) > offset + limit,
        "readings": page,
    }


@router.get("/network/recent")
async def get_network_recent(
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0, le=1000),
    as_of: datetime | None = None,
):
    """Return a bounded page from all sensors in a fixed 60-second window."""
    end = _utc(as_of) if as_of else datetime.now(timezone.utc)
    if end > datetime.now(timezone.utc) + timedelta(seconds=1):
        raise HTTPException(status_code=400, detail="as_of cannot be in the future")
    redis_client = await get_redis()
    regions = sorted(await redis_client.smembers("sensor_regions"))
    if not regions:
        return {"as_of": end, "window_start": end - timedelta(seconds=60),
                "offset": offset, "limit": limit, "returned": 0,
                "has_more": False, "readings": []}
    return await run_in_threadpool(_fetch_network_recent, end, limit, offset, regions)


@router.get("/regions/{region_id}/recent")
async def get_region_recent(
    region_id: str,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0, le=1000),
    as_of: datetime | None = None,
):
    end = _utc(as_of) if as_of else datetime.now(timezone.utc)
    if end > datetime.now(timezone.utc) + timedelta(seconds=1):
        raise HTTPException(status_code=400, detail="as_of cannot be in the future")
    return await run_in_threadpool(_fetch_network_recent, end, limit, offset, [region_id])


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
    latest = _fetch_readings(sensor_id, 1, None)
    if not latest:
        return None
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    rows = _fetch_readings(sensor_id, 100000, one_hour_ago)
    metrics = {}
    for row in rows:
        metrics.setdefault(row["metric_type"], []).append(row["value"])
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
        "latest": latest[0],
        "last_hour": stats,
    }


@router.get("/{sensor_id}/summary")
async def get_summary(
    sensor_id: str,
    response: Response,
):
    redis_client = await get_redis()

    cache_key = f"sensor_summary:{sensor_id}"

    cached = await redis_client.get(cache_key)

    if cached:
        response.headers["X-Cache"] = "HIT"
        return json.loads(cached)

    response.headers["X-Cache"] = "MISS"

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
