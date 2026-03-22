from fastapi import APIRouter

from src.api.deps import CurrentUser
from src.services.apikey import rate_limiter

router = APIRouter(prefix="/rate-limit", tags=["Rate Limiting"])


@router.get("/status")
async def get_rate_limit_status(
    current_user: CurrentUser,
) -> dict:
    """
    Get current rate limit status and usage.
    """
    current_usage, limit = await rate_limiter.get_current_usage(current_user.id)
    ttl = await rate_limiter.get_ttl(current_user.id)

    return {
        "tier": current_user.subscription_tier,
        "requests_this_minute": current_usage,
        "limit_per_minute": limit,
        "resets_in_seconds": ttl,
        "monthly_usage": current_user.monthly_request_count,
        "monthly_limit": current_user.request_limit,
        "monthly_remaining": max(0, current_user.request_limit - current_user.monthly_request_count),
    }
