import redis.asyncio as redis
import os


redis_client = redis.Redis(
    host=os.environ["REDIS_HOST"],
    port=int(os.environ["REDIS_PORT"]),
    decode_responses=True,
)


async def get_redis():
    return redis_client


async def close_redis():
    await redis_client.aclose()
