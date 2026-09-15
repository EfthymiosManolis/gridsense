import os
import time
import asyncio
import statistics
from pathlib import Path

import asyncpg
from pymongo import MongoClient
from dotenv import load_dotenv


load_dotenv(
    Path(__file__).resolve().parents[1] / ".env"
)


def require_env(name: str) -> str:
    value = os.getenv(name)

    if not value:
        raise RuntimeError(
            f"Required environment variable '{name}' is not set"
        )

    return value


MONGO_URI = require_env("SCRIPT_MONGO_URI")

POSTGRES_HOST = require_env(
    "SCRIPT_POSTGRES_HOST"
)

POSTGRES_PORT = int(
    require_env("SCRIPT_POSTGRES_PORT")
)

POSTGRES_USER = require_env(
    "POSTGRES_USER"
)

POSTGRES_PASSWORD = require_env(
    "POSTGRES_PASSWORD"
)

POSTGRES_DB = require_env(
    "POSTGRES_DB"
)
MONGO_COLLECTION = "equipment_c4"
POSTGRES_TABLE = "equipment_c4"

RUNS = 10
WARMUP_RUNS = 3

def benchmark_mongodb():
    client = MongoClient(MONGO_URI)

    try:
        database = client.get_default_database()
        collection = database[MONGO_COLLECTION]
        client.admin.command("ping")

        queries = {
            "Q1 firmware 3.x": lambda: list(
                collection.find(
                    {
                        "metadata.firmware_version": {
                            "$regex": r"^3\."
                        }
                    },
                    {"_id": 0},
                )
            ),

            "Q2 SmartMeter > 230V": lambda: list(
                collection.find(
                    {
                        "type": "SmartMeter",
                        "rated_voltage": {"$gt": 230},
                    },
                    {"_id": 0},
                )
            ),

            "Q3 count by type": lambda: list(
                collection.aggregate([
                    {
                        "$group": {
                            "_id": "$type",
                            "count": {"$sum": 1},
                        }
                    }
                ])
            ),
        }

        benchmark_results = {}

        for query_name, query_function in queries.items():
            timings = []

            for _ in range(WARMUP_RUNS):
                query_function()

            for _ in range(RUNS):
                start = time.perf_counter_ns()

                result = query_function()

                end = time.perf_counter_ns()

                elapsed_ms = (
                    end - start
                ) / 1_000_000

                timings.append(elapsed_ms)

            benchmark_results[query_name] = timings

        return benchmark_results

    finally:
        client.close()

async def benchmark_postgresql():
    connection = await asyncpg.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        database=POSTGRES_DB,
    )

    try:
        queries = {
            "Q1 firmware 3.x": """
                SELECT
                    asset_id,
                    type,
                    name,
                    rated_voltage,
                    metadata
                FROM equipment_c4
                WHERE metadata->>'firmware_version'
                      LIKE '3.%'
            """,

            "Q2 SmartMeter > 230V": """
                SELECT
                    asset_id,
                    type,
                    name,
                    rated_voltage,
                    metadata
                FROM equipment_c4
                WHERE type = 'SmartMeter'
                  AND rated_voltage > 230
            """,

            "Q3 count by type": """
                SELECT
                    type,
                    COUNT(*)
                FROM equipment_c4
                GROUP BY type
            """,
        }

        benchmark_results = {}

        for query_name, query in queries.items():
            timings = []

            for _ in range(WARMUP_RUNS):
                await connection.fetch(query)

            for _ in range(RUNS):
                start = time.perf_counter_ns()

                result = await connection.fetch(query)

                end = time.perf_counter_ns()

                elapsed_ms = (
                    end - start
                ) / 1_000_000

                timings.append(elapsed_ms)

            benchmark_results[query_name] = timings

        return benchmark_results

    finally:
        await connection.close()

async def main():
    print(
        f"Running C.4 benchmark "
        f"({RUNS} runs per query)..."
    )

    mongo_results = benchmark_mongodb()
    postgres_results = await benchmark_postgresql()

    print("\n=== C.4 Results ===")
    print(
        f"{'Query':<28}"
        f"{'MongoDB mean ms':>18}"
        f"{'PostgreSQL mean ms':>22}"
    )
    print("-" * 68)

    for query_name in mongo_results:
        mongo_mean = statistics.mean(
            mongo_results[query_name]
        )

        postgres_mean = statistics.mean(
            postgres_results[query_name]
        )

        print(
            f"{query_name:<28}"
            f"{mongo_mean:>18.4f}"
            f"{postgres_mean:>22.4f}"
        )


if __name__ == "__main__":
    asyncio.run(main())
