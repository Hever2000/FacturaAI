from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class APIKeyBase(BaseModel):
    """Base API key schema."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    expires_at: datetime | None = None


class APIKeyCreate(APIKeyBase):
    """API key creation schema."""

    pass


class APIKeyResponse(BaseModel):
    """API key response (without the full key)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    key_prefix: str
    description: str | None
    is_active: bool
    is_expired: bool
    is_valid: bool
    last_used_at: datetime | None
    expires_at: datetime | None
    request_count: int
    created_at: datetime


class APIKeyWithSecret(BaseModel):
    """API key response with the secret (only shown once on creation)."""

    id: UUID
    name: str
    key: str
    key_prefix: str
    created_at: datetime
    expires_at: datetime | None
    message: str = (
        "This is the only time the full API key is shown. "
        "Save it securely — it cannot be recovered."
    )


class APIKeyUpdate(BaseModel):
    """API key update schema."""

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    is_active: bool | None = None
    expires_at: datetime | None = None


class APIKeyListResponse(BaseModel):
    """List of API keys response."""

    api_keys: list[APIKeyResponse]
    total: int
