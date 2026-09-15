import os
import asyncpg


pool: asyncpg.Pool | None = None


async def init_postgres_pool():
    global pool

    if pool is None:
        pool = await asyncpg.create_pool(
             host=os.environ["POSTGRES_HOST"],
             port=int(os.environ["POSTGRES_PORT"]),
             user=os.environ["POSTGRES_USER"],
             password=os.environ["POSTGRES_PASSWORD"],
             database=os.environ["POSTGRES_DB"],
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
