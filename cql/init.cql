CREATE KEYSPACE IF NOT EXISTS gridsense
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

USE gridsense;

-- Pattern 1:
-- Last N readings for a specific sensor over a time window.
CREATE TABLE IF NOT EXISTS sensor_readings (
    sensor_id text,
    date_bucket date,
    reading_time timestamp,
    region_id text,
    metric_type text,
    value float,
    unit text,
    quality_flag tinyint,
    PRIMARY KEY ((sensor_id, date_bucket), reading_time, metric_type)
) WITH CLUSTERING ORDER BY (reading_time DESC, metric_type ASC)
  AND default_time_to_live = 7776000;

-- Relay operations ordered by event_time for forensic replay.
CREATE TABLE IF NOT EXISTS relay_events (
    feeder_id text,
    event_time timeuuid,
    relay_id text,
    event_type text,
    fault_type text,
    current_kA float,
    PRIMARY KEY ((feeder_id), event_time)
) WITH CLUSTERING ORDER BY (event_time ASC);

-- Pattern 2: recent readings by region, with daily buckets and write shards.
CREATE TABLE IF NOT EXISTS regional_readings (
    region_id text,
    date_bucket date,
    shard tinyint,
    reading_time timestamp,
    sensor_id text,
    metric_type text,
    value float,
    unit text,
    quality_flag tinyint,
    PRIMARY KEY ((region_id, date_bucket, shard), reading_time, sensor_id, metric_type)
) WITH CLUSTERING ORDER BY (
    reading_time DESC,
    sensor_id ASC,
    metric_type ASC
)
AND default_time_to_live = 7776000;

-- Stable identity and completion state of the synthetic sensor dataset.
-- No TTL: completed seed data expires naturally without being recreated.
CREATE TABLE IF NOT EXISTS seed_state (
    name text PRIMARY KEY,
    start_time timestamp,
    completed boolean
);
