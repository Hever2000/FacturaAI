from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import verify_access_token
from src.db import get_db
from src.models.user import User
from src.services.apikey import APIKeyService, rate_limiter
from src.services.auth import AuthService

security = HTTPBearer(auto_error=False)
api_key_security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Get the current authenticated user from JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise credentials_exception

    token = credentials.credentials
    user_id = verify_access_token(token)

    if user_id is None:
        raise credentials_exception

    auth_service = AuthService(db)
    user = await auth_service.get_user_by_id(UUID(user_id))

    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )

    return user


async def get_current_user_via_api_key(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(api_key_security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    Authenticate user via API key (Bearer token format).
    API keys are prefixed with 'fa_' and stored as SHA256 hashes.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    service = APIKeyService(db)
    api_key = await service.validate_api_key(credentials.credentials)

    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    auth_service = AuthService(db)
    user = await auth_service.get_user_by_id(api_key.user_id)

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return user


async def get_current_user_or_api_key(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    api_key_credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(api_key_security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    Get current user via JWT or API key. API key takes precedence if provided.
    """
    if api_key_credentials is not None:
        service = APIKeyService(db)
        api_key = await service.validate_api_key(api_key_credentials.credentials)
        if api_key is not None:
            auth_service = AuthService(db)
            user = await auth_service.get_user_by_id(api_key.user_id)
            if user and user.is_active:
                return user

    return await get_current_user(credentials, db)


async def check_rate_limit(user: User) -> None:
    """Check and enforce rate limit for a user."""
    allowed, current, limit = await rate_limiter.is_allowed(user.id, user.subscription_tier)
    if not allowed:
        ttl = await rate_limiter.get_ttl(user.id)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. {current}/{limit} requests per minute. Resets in {ttl}s.",
            headers={
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(ttl),
                "Retry-After": str(ttl),
            },
        )


async def check_monthly_quota(user: User) -> None:
    """Check if user has remaining monthly quota."""
    if user.monthly_request_count >= user.request_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Monthly quota exceeded. Upgrade your plan at /v1/subscriptions.",
        )


async def get_current_superuser(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Get the current user and verify they are a superuser."""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    return current_user


async def get_optional_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User | None:
    """Get the current user if authenticated, None otherwise."""
    if credentials is None:
        return None

    token = credentials.credentials
    user_id = verify_access_token(token)

    if user_id is None:
        return None

    auth_service = AuthService(db)
    user = await auth_service.get_user_by_id(UUID(user_id))

    if user is None or not user.is_active:
        return None

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentSuperuser = Annotated[User, Depends(get_current_superuser)]
OptionalUser = Annotated[User | None, Depends(get_optional_current_user)]
APIKeyUser = Annotated[User, Depends(get_current_user_via_api_key)]
AnyUser = Annotated[User, Depends(get_current_user_or_api_key)]
DBSession = Annotated[AsyncSession, Depends(get_db)]
RateLimitedUser = Annotated[User, Depends(get_current_user)]
