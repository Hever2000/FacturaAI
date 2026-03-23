from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.db.redis import redis_service, redis_available


class RateLimiter:
    """Redis-based rate limiter using sliding window. Falls back to allow all if Redis unavailable."""

    WINDOW_SECONDS = 60

    async def is_allowed(self, user_id: UUID, tier: str = "free") -> tuple[bool, int, int]:
        """
        Check if request is allowed under rate limit.

        Returns:
            Tuple of (is_allowed, current_count, limit)
        """
        key = f"rate_limit:{user_id}"

        limit = settings.RATE_LIMIT_PER_MINUTE
        if tier == "pro":
            limit = limit * 5
        elif tier == "enterprise":
            limit = limit * 10

        if not redis_available:
            return True, 0, limit

        current = await redis_service.get(key)
        current_count = int(current) if current else 0

        if current_count >= limit:
            return False, current_count, limit

        pipe = await redis_service.pipeline()
        if pipe is None:
            return True, current_count, limit
        
        pipe.incr(key)
        pipe.expire(key, self.WINDOW_SECONDS)
        await pipe.execute()

        return True, current_count + 1, limit

    async def get_current_usage(self, user_id: UUID) -> tuple[int, int]:
        """Get current rate limit usage."""
        if not redis_available:
            return 0, settings.RATE_LIMIT_PER_MINUTE
        
        key = f"rate_limit:{user_id}"
        current = await redis_service.get(key)
        return int(current) if current else 0, settings.RATE_LIMIT_PER_MINUTE

    async def get_ttl(self, user_id: UUID) -> int:
        """Get seconds until rate limit resets."""
        if not redis_available:
            return 0
        
        key = f"rate_limit:{user_id}"
        ttl = await redis_service.ttl(key)
        return max(0, ttl)


class APIKeyService:
    """Service for API key operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_api_key(
        self,
        user_id: UUID,
        name: str,
        description: str | None = None,
        expires_at: datetime | None = None,
    ) -> tuple[APIKey, str]:
        """
        Create a new API key for a user.

        Returns:
            Tuple of (APIKey model, plain_key)
        """
        plain_key, key_hash, key_prefix = APIKey.generate_key()

        api_key = APIKey(
            user_id=user_id,
            name=name,
            key_hash=key_hash,
            key_prefix=key_prefix,
            description=description,
            expires_at=expires_at,
        )
        self.db.add(api_key)
        await self.db.flush()
        await self.db.refresh(api_key)

        return api_key, plain_key

    async def get_api_key_by_id(self, api_key_id: UUID, user_id: UUID) -> APIKey | None:
        """Get an API key by ID for a specific user."""
        result = await self.db.execute(
            select(APIKey).where(
                APIKey.id == api_key_id,
                APIKey.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_api_keys(self, user_id: UUID) -> list[APIKey]:
        """List all API keys for a user."""
        result = await self.db.execute(
            select(APIKey).where(APIKey.user_id == user_id).order_by(APIKey.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_api_key(
        self,
        api_key: APIKey,
        name: str | None = None,
        description: str | None = None,
        is_active: bool | None = None,
        expires_at: datetime | None = None,
    ) -> APIKey:
        """Update an API key."""
        if name is not None:
            api_key.name = name
        if description is not None:
            api_key.description = description
        if is_active is not None:
            api_key.is_active = is_active
        if expires_at is not None:
            api_key.expires_at = expires_at

        await self.db.flush()
        await self.db.refresh(api_key)
        return api_key

    async def rotate_api_key(self, api_key: APIKey) -> str:
        """
        Rotate an API key.

        Returns:
            New plain key (only shown once).
        """
        new_key = api_key.rotate()
        await self.db.flush()
        await self.db.refresh(api_key)
        return new_key

    async def delete_api_key(self, api_key: APIKey) -> None:
        """Delete an API key."""
        await self.db.delete(api_key)
        await self.db.flush()

    async def validate_api_key(self, plain_key: str) -> APIKey | None:
        """
        Validate a plain API key against stored hashes.

        Returns:
            APIKey if valid, None otherwise.
        """
        import hashlib

        if not plain_key.startswith("fa_"):
            return None

        key_prefix = plain_key[:15]
        key_hash = hashlib.sha256(plain_key.encode()).hexdigest()

        result = await self.db.execute(
            select(APIKey).where(
                APIKey.key_prefix == key_prefix,
                APIKey.key_hash == key_hash,
                APIKey.is_active == True,  # noqa: E712
            )
        )
        api_key = result.scalar_one_or_none()

        if api_key is None:
            return None

        if api_key.is_expired:
            return None

        api_key.last_used_at = datetime.now(UTC)
        api_key.request_count += 1
        await self.db.flush()

        return api_key

    async def increment_usage(self, api_key: APIKey) -> None:
        """Increment API key usage counter."""
        api_key.request_count += 1
        api_key.last_used_at = datetime.now(UTC)
        await self.db.flush()


rate_limiter = RateLimiter()
