import time
import math
import statistics
import json
import urllib.request
import matplotlib.pyplot as plt


BASE_URL = "http://127.0.0.1:8000"
NODE_ID = "GSP001"

DEPTHS = range(1, 7)
ITERATIONS_PER_DEPTH = 30
WARMUP_ITERATIONS = 5

def measure_request(depth):
    url = (
        f"{BASE_URL}/grid/fault-impact/"
        f"{NODE_ID}?max_depth={depth}"
    )

    start_time = time.perf_counter()

    with urllib.request.urlopen(
        url,
        timeout=10
    ) as response:
        body = response.read()

    latency_ms = (
        time.perf_counter() - start_time
    ) * 1000.0

    data = json.loads(body)

    return latency_ms, data["total_affected"]

def benchmark_depth(depth):
    latencies = []
    expected_total = None

    print(
        f"Testing max_depth={depth} "
        f"({ITERATIONS_PER_DEPTH} iterations)"
    )

    for _ in range(WARMUP_ITERATIONS):
        measure_request(depth)

    for iteration in range(ITERATIONS_PER_DEPTH):
        latency_ms, total_affected = measure_request(depth)

        latencies.append(latency_ms)

        if expected_total is None:
            expected_total = total_affected
        elif total_affected != expected_total:
            raise RuntimeError(
                f"Inconsistent total_affected at depth {depth}: "
                f"expected {expected_total}, got {total_affected}"
            )

    return latencies, expected_total

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

def summarize_depth(depth, latencies, total_affected):
    median_ms = statistics.median(latencies)
    p95_ms = percentile(latencies, 95)

    return {
        "depth": depth,
        "median_ms": median_ms,
        "p95_ms": p95_ms,
        "total_affected": total_affected,
    }


def save_line_chart(results):
    depths = [
        result["depth"]
        for result in results
    ]

    median_values = [
        result["median_ms"]
        for result in results
    ]

    p95_values = [
        result["p95_ms"]
        for result in results
    ]

    plt.figure(figsize=(8, 5))

    plt.plot(
        depths,
        median_values,
        marker="o",
        label="Median latency",
    )

    plt.plot(
        depths,
        p95_values,
        marker="o",
        label="p95 latency",
    )

    plt.xlabel("max_depth")
    plt.ylabel("Latency (ms)")
    plt.title(
        "C.2 Graph Traversal Depth vs Latency"
    )

    plt.xticks(depths)
    plt.grid(True)
    plt.legend()
    plt.tight_layout()

    plt.savefig(
        "c2_graph_traversal_latency.png",
        dpi=200,
    )

    plt.close()

def main():
    results = []

    print("=== C.2 Neo4j Traversal Benchmark ===")
    print(f"Node: {NODE_ID}")
    print(
        f"Iterations per depth: "
        f"{ITERATIONS_PER_DEPTH}"
    )

    for depth in DEPTHS:
        latencies, total_affected = benchmark_depth(
            depth
        )

        result = summarize_depth(
            depth,
            latencies,
            total_affected,
        )

        results.append(result)

    print("\n=== C.2 Results ===")

    print(
        f"{'Depth':<8}"
        f"{'Median ms':>14}"
        f"{'p95 ms':>14}"
        f"{'Affected':>12}"
    )

    print("-" * 48)

    for result in results:
        print(
            f"{result['depth']:<8}"
            f"{result['median_ms']:>14.3f}"
            f"{result['p95_ms']:>14.3f}"
            f"{result['total_affected']:>12}"
        )
    save_line_chart(results)

    print(
        "\nLine chart saved as "
        "c2_graph_traversal_latency.png"
    )

if __name__ == "__main__":
    main()
