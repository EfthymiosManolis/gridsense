import os
import asyncpg
from pathlib import Path


pool: asyncpg.Pool | None = None


async def apply_billing_schema(connection):
    async with connection.transaction():
        # Concurrent API starts must not race while creating constraints.
        await connection.execute("SELECT pg_advisory_xact_lock(714032601)")
        await connection.execute(Path(__file__).with_name('billing_schema.sql').read_text())


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

        try:
            async with pool.acquire() as connection:
                await apply_billing_schema(connection)
        except Exception:
            await pool.close()
            pool = None
            raise

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
