from neo4j import AsyncGraphDatabase
import os


driver = AsyncGraphDatabase.driver(
    os.environ["NEO4J_URI"],
    auth=(
        os.environ["NEO4J_USER"],
        os.environ["NEO4J_PASSWORD"],
    ),
)


async def get_neo4j_driver():
    return driver


async def close_neo4j_driver():
    await driver.close()
