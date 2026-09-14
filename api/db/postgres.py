import os
import asyncpg


pool: asyncpg.Pool | None = None


async def init_postgres_pool():
    global pool

    if pool is None:
        pool = await asyncpg.create_pool(
            host=os.getenv("POSTGRES_HOST", "billing-db"),
            port=int(os.getenv("POSTGRES_PORT", "5432")),
            user=os.getenv("POSTGRES_USER", "gridsense"),
            password=os.getenv("POSTGRES_PASSWORD"),
            database=os.getenv("POSTGRES_DB", "gridsense"),
            min_size=1,
            max_size=10,
        )

    return pool


def get_postgres_pool():
    if pool is None:
        raise RuntimeError("PostgreSQL pool has not been initialized")

    return pool


async def close_postgres_pool():
    global pool

    if pool is not None:
        await pool.close()
        pool = None
