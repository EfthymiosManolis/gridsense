import os
import time
import math
import statistics
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dotenv import load_dotenv
from cassandra import ConsistencyLevel
from cassandra.cluster import Cluster

load_dotenv(
    Path(__file__).resolve().parents[1] / ".env"
)

CASSANDRA_HOST = os.environ[
    "SCRIPT_CASSANDRA_HOST"
]

CASSANDRA_PORT = int(
    os.environ["SCRIPT_CASSANDRA_PORT"]
)

KEYSPACE = "gridsense"

CONCURRENCY = 32
WARMUP_SECONDS = 5
MEASUREMENT_SECONDS = 15
TRIALS = 5

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
            date_bucket,
            reading_time,
            metric_type,
            value,
            unit,
            quality_flag
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
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
            reading_time.date(),
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
    trial_number,
):
    print(f"\n=== {level_name}"
          f"Trial {trial_number}/{TRIALS}  ==="
    )

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
        f"WARMUP_T{trial_number}",
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
        f"MEASURE_T{trial_number}",
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
        "trial": trial_number,
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
            for trial_number in range(1, TRIALS + 1):
                with ThreadPoolExecutor(
                   max_workers=CONCURRENCY
                ) as executor:
                   result = benchmark_consistency_level(
                       executor,
                       session,
                       insert_statement,
                       consistency_level,
                       level_name,
                       trial_number,
                   )

                   results.append(result)

    finally:
        cluster.shutdown()
    print("\n=== C.1 Individual Trial Results ===")

    print(
        f"{'Consistency':<16}"
        f"{'Trial':>7}"
        f"{'Events/sec':>14}"
        f"{'p50 ms':>12}"
        f"{'p95 ms':>12}"
        f"{'Errors':>10}"
    )

    print("-" * 71)

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
            f"{result['trial']:>7}"
            f"{result['events_per_second']:>14.2f}"
            f"{p50_text:>12}"
            f"{p95_text:>12}"
            f"{result['errors']:>10}"
        )

    print("\n=== C.1 Aggregate Results ===")

    print(
        f"{'Consistency':<16}"
        f"{'Mean ev/s':>14}"
        f"{'Std ev/s':>12}"
        f"{'Mean p50':>12}"
        f"{'Mean p95':>12}"
        f"{'Errors':>10}"
    )

    print("-" * 76)

    for level_name, _ in consistency_levels:
        level_results = [
            result
            for result in results
            if result["consistency"] == level_name
        ]

        throughputs = [
            result["events_per_second"]
            for result in level_results
        ]

        p50_values = [
            result["p50_ms"]
            for result in level_results
            if result["p50_ms"] is not None
        ]

        p95_values = [
            result["p95_ms"]
            for result in level_results
            if result["p95_ms"] is not None
        ]

        mean_throughput = statistics.mean(throughputs)

        if len(throughputs) > 1:
            std_throughput = statistics.stdev(
                throughputs
            )
        else:
            std_throughput = 0.0

        mean_p50 = statistics.mean(p50_values)
        mean_p95 = statistics.mean(p95_values)

        total_errors = sum(
            result["errors"]
            for result in level_results
        )

        print(
            f"{level_name:<16}"
            f"{mean_throughput:>14.2f}"
            f"{std_throughput:>12.2f}"
            f"{mean_p50:>12.3f}"
            f"{mean_p95:>12.3f}"
            f"{total_errors:>10}"
        )


if __name__ == "__main__":
    main()
