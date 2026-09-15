from motor.motor_asyncio import AsyncIOMotorClient
import os


client = AsyncIOMotorClient(
    os.environ["MONGO_URI"]
)

database = client[
    os.environ["MONGO_DB"]
]


def get_mongo_database():
    return database


def close_mongo_client():
    client.close()
