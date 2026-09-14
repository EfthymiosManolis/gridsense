from motor.motor_asyncio import AsyncIOMotorClient
import os


client = AsyncIOMotorClient(
    os.getenv("MONGO_URI", "mongodb://catalog-db:27017")
)

database = client[os.getenv("MONGO_DB", "gridsense")]


def get_mongo_database():
    return database

def close_mongo_client():
    client.close()
