import asyncio

import redis.asyncio as redis

from src.core.config import settings

redis_client: redis.Redis | None = None
_redis_lock = asyncio.Lock()


async def init_redis() -> redis.Redis:
    global redis_client
    redis_client = redis.from_url(settings.redis_url, decode_responses=True)
    await redis_client.ping()
    return redis_client


async def get_redis() -> redis.Redis:
    async with _redis_lock:
        if redis_client is None:
            return await init_redis()
        return redis_client


async def close_redis() -> None:
    global redis_client
    if redis_client:
        await redis_client.close()
        redis_client = None
