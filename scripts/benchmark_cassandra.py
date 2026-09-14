import os
import time
import math
import statistics
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta

from cassandra import ConsistencyLevel
from cassandra.cluster import Cluster


CASSANDRA_HOST = os.getenv("CASSANDRA_HOST", "127.0.0.1")
CASSANDRA_PORT = int(os.getenv("CASSANDRA_PORT", "9042"))
KEYSPACE = "gridsense"

CONCURRENCY = 32
WARMUP_SECONDS = 5
MEASUREMENT_SECONDS = 15


def create_cassandra_connection():
    cluster = Cluster(
        [CASSANDRA_HOST],
        port=CASSANDRA_PORT
    )

    session = cluster.connect(KEYSPACE)

    insert_statement = session.prepare("""
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
    """)

    return cluster, session, insert_statement

def execute_write(
    session,
    insert_statement,
    consistency_level,
    sensor_id,
    reading_time,
    value
):
    bound_statement = insert_statement.bind(
        (
            sensor_id,
            reading_time,
            "voltage",
            float(value),
            "V",
            0,
        )
    )

    bound_statement.consistency_level = consistency_level

    start_time = time.perf_counter()

    try:
        session.execute(bound_statement)
    except Exception as error:
        return None, str(error)

    latency_ms = (
        time.perf_counter() - start_time
    ) * 1000.0

    return latency_ms, None

def worker_loop(
    session,
    insert_statement,
    consistency_level,
    level_name,
    phase_name,
    worker_id,
    deadline,
    collect_metrics,
):
    latencies = []
    errors = 0
    write_number = 0

    sensor_id =(
        f"C1_{level_name}_{phase_name}_W{worker_id:02d}"
    )

    base_time = datetime.now(timezone.utc)

    while time.perf_counter() < deadline:
        value = 230.0 + (write_number % 20) * 0.1

        reading_time = base_time + timedelta(
            milliseconds=write_number
        )

        latency_ms, error = execute_write(
            session,
            insert_statement,
            consistency_level,
            sensor_id,
            reading_time,
            value,
        )

        if error is None:
            if collect_metrics:
                latencies.append(latency_ms)
        else:
            errors += 1

        write_number += 1

    return latencies, errors

def run_phase(
    executor,
    session,
    insert_statement,
    consistency_level,
    level_name,
    phase_name,
    duration_seconds,
    collect_metrics,
):
    start_time = time.perf_counter()
    deadline = start_time + duration_seconds

    futures = []

    for worker_id in range(CONCURRENCY):
        future = executor.submit(
            worker_loop,
            session,
            insert_statement,
            consistency_level,
            level_name,
            phase_name,
            worker_id,
            deadline,
            collect_metrics,
        )
        futures.append(future)

    all_latencies = []
    total_errors = 0

    for future in futures:
        latencies, errors = future.result()
        all_latencies.extend(latencies)
        total_errors += errors

    elapsed_seconds = time.perf_counter() - start_time

    return all_latencies, total_errors, elapsed_seconds


def percentile(values, percent):
    if not values:
        return None

    ordered_values = sorted(values)

    index = math.ceil(
        (percent / 100.0) * len(ordered_values)
    ) - 1

    index = max(
        0,
        min(index, len(ordered_values) - 1)
    )

    return ordered_values[index]

def benchmark_consistency_level(
    executor,
    session,
    insert_statement,
    consistency_level,
    level_name,
):
    print(f"\n=== {level_name} ===")
    print(
        f"Warm-up: {WARMUP_SECONDS} seconds "
        f"with concurrency {CONCURRENCY}"
    )

    _, warmup_errors, _ = run_phase(
        executor,
        session,
        insert_statement,
        consistency_level,
        level_name,
        "WARMUP",
        WARMUP_SECONDS,
        False,
    )

    if warmup_errors > 0:
        print(
            f"Warm-up errors observed: "
            f"{warmup_errors}"
        )

    print(
        f"Measurement: {MEASUREMENT_SECONDS} seconds"
    )

    latencies, errors, elapsed_seconds = run_phase(
        executor,
        session,
        insert_statement,
        consistency_level,
        level_name,
        "MEASURE",
        MEASUREMENT_SECONDS,
        True,
    )

    successful_writes = len(latencies)

    if elapsed_seconds > 0:
        events_per_second = (
            successful_writes / elapsed_seconds
        )
    else:
        events_per_second = 0.0

    if latencies:
        p50_ms = statistics.median(latencies)
        p95_ms = percentile(latencies, 95)
    else:
        p50_ms = None
        p95_ms = None

    return {
        "consistency": level_name,
        "successful_writes": successful_writes,
        "events_per_second": events_per_second,
        "p50_ms": p50_ms,
        "p95_ms": p95_ms,
        "errors": errors,
        "elapsed_seconds": elapsed_seconds,
    }

def main():
    cluster, session, insert_statement = (
        create_cassandra_connection()
    )

    consistency_levels = [
        ("ONE", ConsistencyLevel.ONE),
        (
            "LOCAL_QUORUM",
            ConsistencyLevel.LOCAL_QUORUM,
        ),
        ("ALL", ConsistencyLevel.ALL),
    ]

    results = []

    try:
        for level_name, consistency_level in consistency_levels:
            with ThreadPoolExecutor(
                max_workers=CONCURRENCY
            ) as executor:
                result = benchmark_consistency_level(
                    executor,
                    session,
                    insert_statement,
                    consistency_level,
                    level_name,
                )

                results.append(result)

    finally:
        cluster.shutdown()

    print("\n=== C.1 Cassandra Benchmark Results ===")

    print(
        f"{'Consistency':<16}"
        f"{'Events/sec':>14}"
        f"{'p50 ms':>12}"
        f"{'p95 ms':>12}"
        f"{'Errors':>10}"
    )

    print("-" * 64)

    for result in results:
        if result["p50_ms"] is None:
            p50_text = "N/A"
        else:
            p50_text = f"{result['p50_ms']:.3f}"

        if result["p95_ms"] is None:
            p95_text = "N/A"
        else:
            p95_text = f"{result['p95_ms']:.3f}"

        print(
            f"{result['consistency']:<16}"
            f"{result['events_per_second']:>14.2f}"
            f"{p50_text:>12}"
            f"{p95_text:>12}"
            f"{result['errors']:>10}"
        )


if __name__ == "__main__":
    main()
