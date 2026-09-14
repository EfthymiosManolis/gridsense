from neo4j import AsyncGraphDatabase
import os


driver = AsyncGraphDatabase.driver(
    os.getenv("NEO4J_URI", "bolt://graph-db:7687"),
    auth=(
        "neo4j",
        os.getenv("NEO4J_PASSWORD")
    )
)


async def get_neo4j_driver():
    return driver


async def close_neo4j_driver():
    await driver.close()
