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
    reading_time timestamp,
    metric_type text,
    value float,
    unit text,
    quality_flag tinyint,
    PRIMARY KEY ((sensor_id), reading_time)
) WITH CLUSTERING ORDER BY (reading_time DESC)
  AND default_time_to_live = 7776000;

-- Append-only relay operation log.
CREATE TABLE IF NOT EXISTS relay_events (
    feeder_id text,
    event_time timeuuid,
    relay_id text,
    event_type text,
    fault_type text,
    current_kA float,
    PRIMARY KEY ((feeder_id), event_time)
) WITH CLUSTERING ORDER BY (event_time ASC);

-- Pattern 2:
-- Recent readings across the whole network for the live dashboard.
--
-- Time bucketing prevents an unbounded partition.
-- Sharding prevents all network writes from hitting one partition.
CREATE TABLE IF NOT EXISTS dashboard_readings (
    bucket_minute timestamp,
    shard tinyint,
    reading_time timestamp,
    sensor_id text,
    metric_type text,
    value float,
    unit text,
    quality_flag tinyint,
    PRIMARY KEY ((bucket_minute, shard), reading_time, sensor_id, metric_type)
) WITH CLUSTERING ORDER BY (
    reading_time DESC,
    sensor_id ASC,
    metric_type ASC
)
AND default_time_to_live = 7776000;
