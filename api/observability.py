from collections import defaultdict, deque
from time import perf_counter
from threading import Lock

from fastapi import Request


MAX_LATENCY_SAMPLES = 1000

_stats = defaultdict(
    lambda: {
        "request_count": 0,
        "error_count": 0,
        "latencies_ms": deque(maxlen=MAX_LATENCY_SAMPLES),
    }
)

_lock = Lock()


def _percentile(values, percentile):
    if not values:
        return 0.0

    ordered = sorted(values)

    index = int(
        round((percentile / 100) * (len(ordered) - 1))
    )

    return ordered[index]


async def metrics_middleware(request: Request, call_next):
    start = perf_counter()
    status_code = 500

    try:
        response = await call_next(request)
        status_code = response.status_code
        return response

    finally:
        elapsed_ms = (perf_counter() - start) * 1000

        route = request.scope.get("route")

        if route is not None and hasattr(route, "path"):
            path = route.path
        else:
            path = request.url.path

        key = f"{request.method} {path}"

        with _lock:
            entry = _stats[key]

            entry["request_count"] += 1

            if status_code >= 400:
                entry["error_count"] += 1

            entry["latencies_ms"].append(elapsed_ms)


def get_metrics():
    result = {}

    with _lock:
        for endpoint, entry in _stats.items():
            request_count = entry["request_count"]
            error_count = entry["error_count"]
            latencies = list(entry["latencies_ms"])

            result[endpoint] = {
                "request_count": request_count,
                "error_count": error_count,
                "error_rate": (
                    error_count / request_count
                    if request_count
                    else 0.0
                ),
                "latency_ms": {
                    "p50": round(
                        _percentile(latencies, 50),
                        3,
                    ),
                    "p95": round(
                        _percentile(latencies, 95),
                        3,
                    ),
                    "p99": round(
                        _percentile(latencies, 99),
                        3,
                    ),
                },
            }

    return result
