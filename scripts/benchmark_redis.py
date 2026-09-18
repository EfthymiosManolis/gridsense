import time
import math
import statistics
import subprocess
import urllib.request


BASE_URL = "http://127.0.0.1:8000"

SENSOR_ID = "SENSOR01"
SUMMARY_URL = (
    f"{BASE_URL}/sensors/{SENSOR_ID}/summary"
)

CACHE_KEY = f"sensor_summary:{SENSOR_ID}"

REQUESTS_PER_BATCH = 500
CACHE_TTL_SECONDS = 30

def measure_request():
    start_time = time.perf_counter()

    with urllib.request.urlopen(
        SUMMARY_URL,
        timeout=10,
    ) as response:
        response.read()
        cache_status = response.headers.get(
            "X-Cache",
            "UNKNOWN",
        )

    latency_ms = (
        time.perf_counter() - start_time
    ) * 1000.0

    return latency_ms, cache_status

def run_redis_command(*args):
    result = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "cache",
            "redis-cli",
            *args,
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    return result.stdout.strip()


def delete_cache_key():
    run_redis_command(
        "DEL",
        CACHE_KEY,
    )

def run_warm_batch():
    print(
        f"Running warm-cache batch "
        f"({REQUESTS_PER_BATCH} requests)"
    )

    delete_cache_key()

    # Populate cache before measured batch.
    measure_request()

    latencies = []
    hits = 0
    misses = 0

    for _ in range(REQUESTS_PER_BATCH):
        latency_ms, cache_status = measure_request()
        latencies.append(latency_ms)

        if cache_status == "HIT":
            hits += 1
        elif cache_status == "MISS":
            misses += 1

    return latencies, hits, misses

def run_cold_batch():
    print(
        f"Running cold-cache batch "
        f"({REQUESTS_PER_BATCH} requests)"
    )

    latencies = []
    hits = 0
    misses = 0

    for _ in range(REQUESTS_PER_BATCH):
        latency_ms, cache_status = measure_request()
        latencies.append(latency_ms)

        if cache_status == "HIT":
            hits += 1
        elif cache_status == "MISS":
            misses += 1

    return latencies, hits, misses


def percentile(values, percent):
    ordered_values = sorted(values)

    index = math.ceil(
        (percent / 100.0) * len(ordered_values)
    ) - 1

    index = max(
        0,
        min(index, len(ordered_values) - 1)
    )

    return ordered_values[index]


def summarize_batch(
    batch_name,
    latencies,
    hits,
    misses,
):
    p50_ms = statistics.median(latencies)
    p95_ms = percentile(latencies, 95)
    p99_ms = percentile(latencies, 99)

    total_cache_lookups = hits + misses

    if total_cache_lookups > 0:
        hit_rate = (
            hits / total_cache_lookups
        ) * 100.0
    else:
        hit_rate = 0.0

    return {
        "batch": batch_name,
        "p50_ms": p50_ms,
        "p95_ms": p95_ms,
        "p99_ms": p99_ms,
        "hits": hits,
        "misses": misses,
        "hit_rate": hit_rate,
    }

def wait_for_cache_expiry():
    print(
        f"\nWaiting for Redis TTL "
        f"({CACHE_TTL_SECONDS} seconds) to expire..."
    )

    while True:
        ttl = int(
            run_redis_command(
                "TTL",
                CACHE_KEY,
            )
        )

        if ttl == -2:
            break

        time.sleep(1)

    print("Cache key expired.")

def main():
    print("=== C.3 Redis Cache Benchmark ===")
    print(f"Sensor: {SENSOR_ID}")
    print(
        f"Requests per batch: "
        f"{REQUESTS_PER_BATCH}"
    )
    print(
        f"Cache TTL: "
        f"{CACHE_TTL_SECONDS} seconds"
    )

    warm_latencies, warm_hits, warm_misses = (
        run_warm_batch()
    )

    warm_result = summarize_batch(
        "WARM",
        warm_latencies,
        warm_hits,
        warm_misses,
    )

    wait_for_cache_expiry()

    cold_latencies, cold_hits, cold_misses = (
        run_cold_batch()
    )

    cold_result = summarize_batch(
        "COLD",
        cold_latencies,
        cold_hits,
        cold_misses,
    )

    results = [
        warm_result,
        cold_result,
    ]

    print("\n=== C.3 Results ===")

    print(
        f"{'Batch':<10}"
        f"{'p50 ms':>12}"
        f"{'p95 ms':>12}"
        f"{'p99 ms':>12}"
        f"{'Hits':>10}"
        f"{'Misses':>10}"
        f"{'Hit rate':>12}"
    )

    print("-" * 78)

    for result in results:
        print(
            f"{result['batch']:<10}"
            f"{result['p50_ms']:>12.3f}"
            f"{result['p95_ms']:>12.3f}"
            f"{result['p99_ms']:>12.3f}"
            f"{result['hits']:>10}"
            f"{result['misses']:>10}"
            f"{result['hit_rate']:>11.2f}%"
        )
    run_controlled_comparison()


def run_controlled_comparison():
    samples = 30

    print("\n=== C.3 Supplemental Hit-vs-Miss Test ===")
    print(f"Samples per condition: {samples}")

    delete_cache_key()
    measure_request()

    hit_latencies = []

    for _ in range(samples):
        latency_ms, _ = measure_request()
        hit_latencies.append(latency_ms)

    # Controlled cache misses
    miss_latencies = []

    for _ in range(samples):
        delete_cache_key()
        latency_ms, _ = measure_request()
        miss_latencies.append(latency_ms)

    hit_median = statistics.median(hit_latencies)
    miss_median = statistics.median(miss_latencies)

    incremental_miss_ms = miss_median - hit_median

    baseline_fraction = (
        hit_median / miss_median * 100.0
        if miss_median > 0
        else 0.0
    )

    incremental_fraction = (
        incremental_miss_ms / miss_median * 100.0
        if miss_median > 0
        else 0.0
    )

    print(f"Hit median: {hit_median:.3f} ms")
    print(f"Miss median: {miss_median:.3f} ms")
    print(
        f"Incremental miss cost: "
        f"{incremental_miss_ms:.3f} ms"
    )
    print(
        f"Baseline HTTP/API/cache-hit fraction: "
        f"{baseline_fraction:.2f}%"
    )
    print(
        f"Incremental miss-path fraction: "
        f"{incremental_fraction:.2f}%"
    )



if __name__ == "__main__":
    main()
