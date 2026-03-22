from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SubscriptionPlan(BaseModel):
    """Available subscription plan."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    price: float
    currency_id: str = "ARS"
    monthly_limit: int
    rate_limit_per_minute: int
    description: str


class SubscriptionCheckoutRequest(BaseModel):
    """Request to create a subscription checkout."""

    tier: str = Field(..., pattern="^(pro|enterprise)$")


class SubscriptionCheckoutResponse(BaseModel):
    """Response with MP checkout URL."""

    preapproval_id: str
    init_point: str
    sandbox_init_point: str | None = None


class CurrentSubscriptionResponse(BaseModel):
    """Current user subscription status."""

    tier: str
    status: str | None
    external_id: str | None
    expires_at: datetime | None
    monthly_limit: int
    monthly_used: int
    monthly_remaining: int


class MessageResponse(BaseModel):
    """Generic message response."""

    message: str
