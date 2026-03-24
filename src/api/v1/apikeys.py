from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from src.api.deps import CurrentUser, DBSession
from src.schemas.apikey import (
    APIKeyCreate,
    APIKeyListResponse,
    APIKeyResponse,
    APIKeyUpdate,
    APIKeyWithSecret,
)
from src.services.apikey import APIKeyService

router = APIRouter(prefix="/apikeys", tags=["API Keys"])


@router.post("", response_model=APIKeyWithSecret, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    api_key_data: APIKeyCreate,
    db: DBSession,
    current_user: CurrentUser,
) -> APIKeyWithSecret:
    """Create a new API key for programmatic access."""
    service = APIKeyService(db)
    api_key, plain_key = await service.create_api_key(
        user_id=current_user.id,
        name=api_key_data.name,
        description=api_key_data.description,
        expires_at=api_key_data.expires_at,
        scopes=api_key_data.scopes,
    )
    return APIKeyWithSecret(
        id=api_key.id,
        name=api_key.name,
        key=plain_key,
        key_prefix=api_key.key_prefix,
        scopes=api_key.scopes,
        created_at=api_key.created_at,
        expires_at=api_key.expires_at,
    )


@router.get("", response_model=APIKeyListResponse)
async def list_api_keys(
    db: DBSession,
    current_user: CurrentUser,
) -> APIKeyListResponse:
    """List all API keys for the current user."""
    service = APIKeyService(db)
    api_keys = await service.list_api_keys(current_user.id)
    return APIKeyListResponse(
        api_keys=[APIKeyResponse.model_validate(k) for k in api_keys],
        total=len(api_keys),
    )


@router.get("/{api_key_id}", response_model=APIKeyResponse)
async def get_api_key(
    api_key_id: UUID,
    db: DBSession,
    current_user: CurrentUser,
) -> APIKeyResponse:
    """Get a specific API key by ID."""
    service = APIKeyService(db)
    api_key = await service.get_api_key_by_id(api_key_id, current_user.id)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
    return APIKeyResponse.model_validate(api_key)


@router.patch("/{api_key_id}", response_model=APIKeyResponse)
async def update_api_key(
    api_key_id: UUID,
    update_data: APIKeyUpdate,
    db: DBSession,
    current_user: CurrentUser,
) -> APIKeyResponse:
    """Update an API key (name, description, scopes, rate limit, active status, expiry)."""
    service = APIKeyService(db)
    api_key = await service.get_api_key_by_id(api_key_id, current_user.id)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
    updated = await service.update_api_key(
        api_key,
        name=update_data.name,
        description=update_data.description,
        is_active=update_data.is_active,
        expires_at=update_data.expires_at,
        scopes=update_data.scopes,
        rate_limit_per_minute=update_data.rate_limit_per_minute,
    )
    return APIKeyResponse.model_validate(updated)


@router.post("/{api_key_id}/rotate", response_model=APIKeyWithSecret)
async def rotate_api_key(
    api_key_id: UUID,
    db: DBSession,
    current_user: CurrentUser,
) -> APIKeyWithSecret:
    """Rotate an API key. The old key is invalidated and a new one is returned."""
    service = APIKeyService(db)
    api_key = await service.get_api_key_by_id(api_key_id, current_user.id)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
    new_key = await service.rotate_api_key(api_key)
    return APIKeyWithSecret(
        id=api_key.id,
        name=api_key.name,
        key=new_key,
        key_prefix=api_key.key_prefix,
        scopes=api_key.scopes,
        created_at=api_key.created_at,
        expires_at=api_key.expires_at,
    )


@router.delete("/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    api_key_id: UUID,
    db: DBSession,
    current_user: CurrentUser,
) -> None:
    """Delete an API key permanently."""
    service = APIKeyService(db)
    api_key = await service.get_api_key_by_id(api_key_id, current_user.id)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found",
        )
    await service.delete_api_key(api_key)
