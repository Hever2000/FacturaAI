from fastapi import APIRouter, HTTPException, Request, status

from src.api.deps import CurrentUser, DBSession
from src.schemas.subscription import (
    CurrentSubscriptionResponse,
    MessageResponse,
    SubscriptionCheckoutRequest,
    SubscriptionCheckoutResponse,
    SubscriptionPlan,
)
from src.services.subscription import PLANS, SubscriptionService

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


@router.get("/plans", response_model=list[SubscriptionPlan])
async def list_plans() -> list[SubscriptionPlan]:
    """List all available subscription plans."""
    return list(PLANS.values())


@router.post(
    "", response_model=SubscriptionCheckoutResponse, status_code=status.HTTP_201_CREATED
)
async def create_subscription(
    subscription_request: SubscriptionCheckoutRequest,
    request: Request,
    db: DBSession,
    current_user: CurrentUser,
) -> SubscriptionCheckoutResponse:
    """
    Create a new subscription.

    Creates a Mercado Pago checkout for a subscription tier.
    Returns the MP checkout URL (init_point) to redirect the user.
    """
    tier = subscription_request.tier

    if tier not in PLANS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid tier. Available: {list(PLANS.keys())}",
        )

    if current_user.subscription_tier == tier and current_user.subscription_status == "authorized":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You already have an active subscription for this tier",
        )

    base_url = str(request.base_url).rstrip("/")
    service = SubscriptionService(db)

    try:
        return await service.create_checkout(
            user=current_user,
            tier=tier,
            base_url=base_url,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to create subscription: {str(e)}",
        )


@router.get("/current", response_model=CurrentSubscriptionResponse)
async def get_current_subscription(
    db: DBSession,
    current_user: CurrentUser,
) -> CurrentSubscriptionResponse:
    """Get current user's subscription status."""
    service = SubscriptionService(db)
    return await service.get_current_subscription(current_user)


@router.delete(
    "", response_model=MessageResponse, status_code=status.HTTP_200_OK
)
async def cancel_subscription(
    db: DBSession,
    current_user: CurrentUser,
) -> MessageResponse:
    """Cancel the active subscription. User returns to free tier."""
    if current_user.subscription_tier == "free":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active subscription to cancel",
        )

    service = SubscriptionService(db)
    try:
        result = await service.cancel_subscription(current_user)
        return MessageResponse(message=result["message"])
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to cancel subscription: {str(e)}",
        )


@router.patch("/pause", response_model=MessageResponse)
async def pause_subscription(
    db: DBSession,
    current_user: CurrentUser,
) -> MessageResponse:
    """Pause the active subscription (stops billing)."""
    if current_user.subscription_tier == "free":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active subscription to pause",
        )

    if current_user.subscription_status == "paused":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subscription is already paused",
        )

    service = SubscriptionService(db)
    try:
        result = await service.pause_subscription(current_user)
        return MessageResponse(message=result["message"])
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to pause subscription: {str(e)}",
        )


@router.patch("/resume", response_model=MessageResponse)
async def resume_subscription(
    db: DBSession,
    current_user: CurrentUser,
) -> MessageResponse:
    """Resume a paused subscription."""
    if current_user.subscription_tier == "free":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No subscription to resume",
        )

    if current_user.subscription_status != "paused":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Subscription is not paused",
        )

    service = SubscriptionService(db)
    try:
        result = await service.resume_subscription(current_user)
        return MessageResponse(message=result["message"])
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to resume subscription: {str(e)}",
        )
