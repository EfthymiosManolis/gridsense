import redis.asyncio as redis
import os


redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "cache"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    decode_responses=True
)


async def get_redis():
    return redis_client

async def close_redis():
    await redis_client.aclose()
