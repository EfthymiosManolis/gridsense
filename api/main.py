from contextlib import asynccontextmanager
from api.observability import metrics_middleware, get_metrics
from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool

from api.routers import sensors, grid, equipment, billing, alerts

from api.db.cassandra import init_cassandra, close_cassandra
from api.db.neo4j import get_neo4j_driver, close_neo4j_driver
from api.db.mongo import get_mongo_database, close_mongo_client
from api.db.postgres import init_postgres_pool, close_postgres_pool
from api.db.redis import get_redis, close_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        # Cassandra
        await run_in_threadpool(init_cassandra)

        # PostgreSQL
        await init_postgres_pool()

        # Neo4j
        neo4j_driver = await get_neo4j_driver()
        await neo4j_driver.verify_connectivity()

        # MongoDB
        mongo_database = get_mongo_database()
        await mongo_database.command("ping")

        # Redis
        redis_client = await get_redis()
        await redis_client.ping()

        yield

    finally:
        await close_redis()
        close_mongo_client()
        await close_neo4j_driver()
        await close_postgres_pool()
        await run_in_threadpool(close_cassandra)


def create_app() -> FastAPI:
    app = FastAPI(
        title="GridSense API",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.middleware("http")(metrics_middleware)

    app.include_router(sensors.router)
    app.include_router(grid.router)
    app.include_router(equipment.router)
    app.include_router(billing.router)
    app.include_router(alerts.router)

    @app.get("/")
    async def root():
        return {"message": "GridSense API is running"}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/metrics")
    async def metrics():
        return get_metrics()

    return app


app = create_app()
