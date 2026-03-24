from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.security import (
    blacklist_token,
    check_token_blacklist,
    create_access_token,
    create_refresh_token,
    get_password_hash,
    verify_password,
    verify_refresh_token,
)
from src.models.user import User
from src.schemas.auth import Token, UserCreate


class AuthService:
    """Service for authentication operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user_by_email(self, email: str) -> User | None:
        """Get a user by email."""
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: UUID) -> User | None:
        """Get a user by ID."""
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def create_user(self, user_data: UserCreate) -> User:
        """Create a new user."""
        user = User(
            email=user_data.email,
            full_name=user_data.full_name,
            hashed_password=get_password_hash(user_data.password),
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        return user

    async def authenticate_user(self, email: str, password: str) -> User | None:
        """Authenticate a user by email and password."""
        user = await self.get_user_by_email(email)
        if not user:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        if not user.is_active:
            return None
        return user

    async def create_tokens_for_user(
        self, user: User, token_id: str | None = None
    ) -> Token:
        """Create access and refresh tokens for a user with rotation support."""
        access_token = create_access_token(subject=str(user.id))
        refresh_token, token_id = create_refresh_token(
            subject=str(user.id),
            token_id=token_id,
        )

        return Token(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )

    async def refresh_tokens(self, refresh_token: str) -> Token | None:
        """
        Refresh access token using refresh token with rotation.

        Implements refresh token rotation:
        1. Validate the refresh token
        2. Check if it's blacklisted
        3. Generate new tokens
        4. Blacklist the old token
        """
        payload = verify_refresh_token(refresh_token)
        if not payload:
            return None

        token_id = payload.get("tid")
        if not token_id:
            return None

        is_blacklisted = await check_token_blacklist(token_id)
        if is_blacklisted:
            return None

        user_id = payload.get("sub")
        if not user_id:
            return None

        user = await self.get_user_by_id(UUID(user_id))
        if not user or not user.is_active:
            return None

        new_tokens = await self.create_tokens_for_user(user)

        await blacklist_token(token_id, settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400)

        return new_tokens

    async def logout(self, refresh_token: str) -> bool:
        """
        Logout a user by blacklisting their refresh token.
        """
        payload = verify_refresh_token(refresh_token)
        if not payload:
            return False

        token_id = payload.get("tid")
        if not token_id:
            return False

        exp = payload.get("exp")
        if exp:
            exp_datetime = datetime.fromtimestamp(exp, UTC)
            ttl = int((exp_datetime - datetime.now(UTC)).total_seconds())
            if ttl > 0:
                await blacklist_token(token_id, ttl)
                return True

        return False

    async def check_usage_and_increment(
        self, user: User, reset_if_needed: bool = True
    ) -> tuple[bool, int, int]:
        """
        Check if user has remaining quota and increment usage.

        Returns:
            Tuple of (has_quota, current_usage, limit)
        """
        now = datetime.now(UTC)

        if (
            reset_if_needed
            and user.monthly_reset_at
            and (now.month != user.monthly_reset_at.month or now.year != user.monthly_reset_at.year)
        ):
            user.monthly_request_count = 0
            user.monthly_reset_at = now

        limit = user.request_limit
        current = user.monthly_request_count

        if current >= limit:
            return False, current, limit

        user.monthly_request_count = current + 1
        await self.db.flush()

        return True, user.monthly_request_count, limit
