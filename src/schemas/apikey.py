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

    scopes: list[str] | None = Field(
        default=["jobs:read", "jobs:write"],
        description="Permissions for the API key (jobs:read, jobs:write)",
    )


class APIKeyResponse(BaseModel):
    """API key response (without the full key)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    key_prefix: str
    description: str | None
    scopes: list[str]
    is_active: bool
    is_expired: bool
    is_valid: bool
    last_used_at: datetime | None
    expires_at: datetime | None
    request_count: int
    rate_limit_per_minute: int
    created_at: datetime


class APIKeyWithSecret(BaseModel):
    """API key response with the secret (only shown once on creation)."""

    id: UUID
    name: str
    key: str
    key_prefix: str
    scopes: list[str]
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
    scopes: list[str] | None = Field(
        None,
        description="Permissions for the API key (jobs:read, jobs:write)",
    )
    is_active: bool | None = None
    expires_at: datetime | None = None
    rate_limit_per_minute: int | None = Field(
        None,
        ge=1,
        le=1000,
        description="Rate limit per minute for this API key",
    )


class APIKeyListResponse(BaseModel):
    """List of API keys response."""

    api_keys: list[APIKeyResponse]
    total: int


VALID_SCOPES = ["jobs:read", "jobs:write"]


def validate_scopes(scopes: list[str]) -> list[str]:
    """Validate that all provided scopes are valid."""
    invalid = [s for s in scopes if s not in VALID_SCOPES]
    if invalid:
        raise ValueError(f"Invalid scopes: {invalid}. Valid scopes: {VALID_SCOPES}")
    return scopes
