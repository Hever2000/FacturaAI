import logging
import random
import time
from typing import Any

import redis.asyncio as redis

from src.core.config import settings

logger = logging.getLogger(__name__)

redis_client: redis.Redis | None = None
redis_available: bool = False

MAX_RETRIES = 5
INITIAL_DELAY = 1
MAX_DELAY = 4


async def _connect_with_retry() -> redis.Redis | None:
    """
    Attempt to connect to Redis with exponential backoff retry.
    
    Returns Redis client if successful, None if all retries fail.
    """
    last_error = None
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            client = redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            await client.ping()
            logger.info(f"Redis connected successfully on attempt {attempt}")
            return client
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES:
                delay = min(INITIAL_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 1), MAX_DELAY)
                logger.warning(f"Redis connection attempt {attempt}/{MAX_RETRIES} failed: {e}. Retrying in {delay:.1f}s...")
                time.sleep(delay)
            else:
                logger.error(f"Redis connection failed after {MAX_RETRIES} attempts: {e}")
    
    return None


async def init_redis() -> bool:
    """
    Initialize Redis connection with retry logic.
    
    Returns True if Redis is available, False otherwise.
    Does NOT crash - app continues even if Redis is unavailable.
    """
    global redis_client, redis_available

    if not settings.REDIS_URL or settings.REDIS_URL.strip() == "":
        logger.info("Redis disabled (no REDIS_URL provided). Running in no-cache mode.")
        redis_available = False
        redis_client = None
        return False

    logger.info(f"Attempting Redis connection to {_redact_url(settings.REDIS_URL)}...")
    
    client = await _connect_with_retry()
    
    if client is not None:
        redis_client = client
        redis_available = True
        logger.info("Redis connection established successfully.")
        return True
    else:
        redis_available = False
        redis_client = None
        logger.warning(
            "Redis unavailable. Running in no-cache mode. "
            "Set REDIS_URL to enable caching (e.g., Upstash, Redis Cloud, Render Redis)."
        )
        return False


async def get_redis() -> redis.Redis | None:
    """Get Redis client instance, initializing if needed."""
    global redis_client
    if redis_client is None:
        await init_redis()
    return redis_client


async def close_redis() -> None:
    """Close Redis connection gracefully."""
    global redis_client, redis_available

    if redis_client is not None:
        try:
            await redis_client.close()
            logger.info("Redis connection closed.")
        except Exception as e:
            logger.warning(f"Error closing Redis: {e}")
        finally:
            redis_client = None
            redis_available = False


def _redact_url(url: str) -> str:
    """Redact credentials from a URL for safe logging."""
    import re
    if not url:
        return ""
    redacted = re.sub(r"://[^@]+@", "://***@", url)
    if "@" not in redacted:
        redacted = re.sub(r"://[^/]+", "://***", url)
    return redacted


class RedisService:
    """
    Safe Redis wrapper with fallback behavior.
    
    If Redis is unavailable, all operations return safe defaults
    without raising exceptions.
    """
    
    @property
    def is_available(self) -> bool:
        """Check if Redis is currently available."""
        return redis_available
    
    async def get(self, key: str) -> str | None:
        """Get value by key. Returns None if Redis unavailable."""
        if not redis_available or redis_client is None:
            return None
        try:
            return await redis_client.get(key)
        except Exception as e:
            logger.warning(f"Redis GET failed for key '{key}': {e}")
            return None
    
    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        """Set key-value pair. Returns False if Redis unavailable."""
        if not redis_available or redis_client is None:
            return False
        try:
            if ex:
                await redis_client.setex(key, ex, value)
            else:
                await redis_client.set(key, value)
            return True
        except Exception as e:
            logger.warning(f"Redis SET failed for key '{key}': {e}")
            return False
    
    async def setex(self, key: str, seconds: int, value: str) -> bool:
        """Set key with expiration. Returns False if Redis unavailable."""
        if not redis_available or redis_client is None:
            return False
        try:
            await redis_client.setex(key, seconds, value)
            return True
        except Exception as e:
            logger.warning(f"Redis SETEX failed for key '{key}': {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """Check if key exists. Returns False if Redis unavailable."""
        if not redis_available or redis_client is None:
            return False
        try:
            result = await redis_client.exists(key)
            return bool(result)
        except Exception as e:
            logger.warning(f"Redis EXISTS failed for key '{key}': {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete key. Returns False if Redis unavailable."""
        if not redis_available or redis_client is None:
            return False
        try:
            await redis_client.delete(key)
            return True
        except Exception as e:
            logger.warning(f"Redis DELETE failed for key '{key}': {e}")
            return False
    
    async def ttl(self, key: str) -> int:
        """Get TTL of key. Returns -1 if Redis unavailable or key doesn't exist."""
        if not redis_available or redis_client is None:
            return -1
        try:
            return await redis_client.ttl(key)
        except Exception as e:
            logger.warning(f"Redis TTL failed for key '{key}': {e}")
            return -1
    
    async def incr(self, key: str) -> int | None:
        """Increment key. Returns None if Redis unavailable."""
        if not redis_available or redis_client is None:
            return None
        try:
            return await redis_client.incr(key)
        except Exception as e:
            logger.warning(f"Redis INCR failed for key '{key}': {e}")
            return None
    
    async def expire(self, key: str, seconds: int) -> bool:
        """Set expiration on key. Returns False if Redis unavailable."""
        if not redis_available or redis_client is None:
            return False
        try:
            await redis_client.expire(key, seconds)
            return True
        except Exception as e:
            logger.warning(f"Redis EXPIRE failed for key '{key}': {e}")
            return False
    
    async def pipeline(self) -> "AsyncPipeline | None":
        """Get Redis pipeline. Returns None if Redis unavailable."""
        if not redis_available or redis_client is None:
            return None
        try:
            return AsyncPipeline(redis_client.pipeline())
        except Exception as e:
            logger.warning(f"Redis PIPELINE failed: {e}")
            return None


class AsyncPipeline:
    """Async wrapper for Redis pipeline."""
    
    def __init__(self, pipeline: Any):
        self._pipeline = pipeline
    
    def incr(self, key: str) -> "AsyncPipeline":
        self._pipeline.incr(key)
        return self
    
    def expire(self, key: str, seconds: int) -> "AsyncPipeline":
        self._pipeline.expire(key, seconds)
        return self
    
    async def execute(self) -> list[Any]:
        try:
            return await self._pipeline.execute()
        except Exception as e:
            logger.warning(f"Pipeline execute failed: {e}")
            return []


redis_service = RedisService()