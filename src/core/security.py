import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from jose import JWTError, jwt
from passlib.context import CryptContext

from src.core.config import settings

ALGORITHM = "HS256"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def create_access_token(
    subject: str | UUID,
    expires_delta: timedelta | None = None,
    extra_claims: dict | None = None,
) -> str:
    """Create a JWT access token."""
    if isinstance(subject, UUID):
        subject = str(subject)

    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode: dict[str, Any] = {
        "exp": expire,
        "sub": subject,
        "type": "access",
    }
    if extra_claims:
        to_encode.update(extra_claims)

    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(
    subject: str | UUID,
    expires_delta: timedelta | None = None,
    token_id: str | None = None,
) -> tuple[str, str]:
    """
    Create a JWT refresh token with rotation support.

    Returns:
        Tuple of (token, token_id)
    """
    if isinstance(subject, UUID):
        subject = str(subject)

    if token_id is None:
        token_id = secrets.token_urlsafe(16)

    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode = {
        "exp": expire,
        "sub": subject,
        "type": "refresh",
        "tid": token_id,
    }

    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt, token_id


def decode_token(token: str) -> dict[str, Any] | None:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def verify_access_token(token: str) -> str | None:
    """Verify an access token and return the subject (user_id)."""
    payload = decode_token(token)
    if payload is None:
        return None
    if payload.get("type") != "access":
        return None
    return payload.get("sub")


def verify_refresh_token(token: str) -> dict[str, Any] | None:
    """
    Verify a refresh token and return the payload.

    Returns:
        Dict with sub, tid (token_id), and exp if valid, None otherwise.
    """
    payload = decode_token(token)
    if payload is None:
        return None
    if payload.get("type") != "refresh":
        return None
    return payload


class TokenBlacklist:
    """Redis-based token blacklist for logout/invalidation."""

    PREFIX = "token_blacklist:"
    DEFAULT_TTL = 86400 * 7

    @classmethod
    async def add(cls, token_id: str, expires_in: int | None = None) -> bool:
        """Add a token to the blacklist."""
        from src.db.redis import redis_service

        if not redis_service.is_available:
            return False

        ttl = expires_in or cls.DEFAULT_TTL
        return await redis_service.setex(
            f"{cls.PREFIX}{token_id}",
            ttl,
            "1"
        )

    @classmethod
    async def is_blacklisted(cls, token_id: str) -> bool:
        """Check if a token is blacklisted."""
        from src.db.redis import redis_service

        if not redis_service.is_available:
            return False

        return await redis_service.exists(f"{cls.PREFIX}{token_id}")


async def check_token_blacklist(token_id: str) -> bool:
    """Check if a token ID is blacklisted."""
    return await TokenBlacklist.is_blacklisted(token_id)


async def blacklist_token(token_id: str, expires_in: int | None = None) -> bool:
    """Blacklist a token (for logout)."""
    return await TokenBlacklist.add(token_id, expires_in)
