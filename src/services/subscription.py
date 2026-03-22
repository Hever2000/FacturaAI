import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user import User
from src.schemas.subscription import (
    CurrentSubscriptionResponse,
    SubscriptionCheckoutResponse,
    SubscriptionPlan,
)

logger = logging.getLogger("facturaai")


PLANS: dict[str, SubscriptionPlan] = {
    "pro": SubscriptionPlan(
        id="pro",
        name="Pro",
        price=1500.0,
        currency_id="ARS",
        monthly_limit=1000,
        rate_limit_per_minute=300,
        description="1000 requests/month, 300 req/min",
    ),
    "enterprise": SubscriptionPlan(
        id="enterprise",
        name="Enterprise",
        price=4500.0,
        currency_id="ARS",
        monthly_limit=10000,
        rate_limit_per_minute=600,
        description="10000 requests/month, 600 req/min",
    ),
}


class SubscriptionService:
    """Service for subscription operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_available_plans(self) -> list[SubscriptionPlan]:
        """Get all available subscription plans."""
        return list(PLANS.values())

    async def get_plan(self, tier: str) -> SubscriptionPlan | None:
        """Get a specific plan by tier."""
        return PLANS.get(tier)

    async def create_checkout(
        self,
        user: User,
        tier: str,
        base_url: str,
    ) -> SubscriptionCheckoutResponse:
        """Create a Mercado Pago checkout for a subscription tier."""
        from src.services.mercadopago import get_mercadopago_client

        plan = PLANS.get(tier)
        if not plan:
            raise ValueError(f"Invalid tier: {tier}")

        client = get_mercadopago_client()
        reason = f"FacturaAI {plan.name} - {user.email}"

        result = await client.create_preapproval(
            tier=tier,
            payer_email=user.email,
            reason=reason,
            back_url=f"{base_url}/dashboard",
        )

        return SubscriptionCheckoutResponse(
            preapproval_id=result["id"],
            init_point=result["init_point"],
            sandbox_init_point=result.get("sandbox_init_point"),
        )

    async def cancel_subscription(self, user: User) -> dict:
        """Cancel user's active subscription."""
        if not user.subscription_external_id:
            raise ValueError("No active subscription found")

        from src.services.mercadopago import get_mercadopago_client

        client = get_mercadopago_client()
        await client.update_preapproval(
            preapproval_id=user.subscription_external_id,
            status="cancelled",
        )

        user.subscription_tier = "free"
        user.subscription_status = "cancelled"
        user.subscription_expires_at = None
        await self.db.flush()

        return {"message": "Subscription cancelled. You are now on the free tier."}

    async def pause_subscription(self, user: User) -> dict:
        """Pause user's active subscription."""
        if not user.subscription_external_id:
            raise ValueError("No active subscription found")

        from src.services.mercadopago import get_mercadopago_client

        client = get_mercadopago_client()
        await client.update_preapproval(
            preapproval_id=user.subscription_external_id,
            status="paused",
        )

        user.subscription_status = "paused"
        await self.db.flush()

        return {"message": "Subscription paused."}

    async def resume_subscription(self, user: User) -> dict:
        """Resume a paused subscription."""
        if not user.subscription_external_id:
            raise ValueError("No active subscription found")

        from src.services.mercadopago import get_mercadopago_client

        client = get_mercadopago_client()
        await client.update_preapproval(
            preapproval_id=user.subscription_external_id,
            status="authorized",
        )

        user.subscription_status = "authorized"
        await self.db.flush()

        return {"message": "Subscription resumed."}

    async def get_current_subscription(self, user: User) -> CurrentSubscriptionResponse:
        """Get current user's subscription status."""
        return CurrentSubscriptionResponse(
            tier=user.subscription_tier,
            status=user.subscription_status,
            external_id=user.subscription_external_id,
            expires_at=user.subscription_expires_at,
            monthly_limit=user.request_limit,
            monthly_used=user.monthly_request_count,
            monthly_remaining=max(0, user.request_limit - user.monthly_request_count),
        )

    async def update_user_from_webhook(
        self,
        preapproval_id: str,
        action: str,
        status: str | None = None,
        plan_id: str | None = None,
    ) -> User | None:
        """
        Update user subscription from webhook notification.

        Actions: preapproval.created, preapproval.updated, preapproval.cancelled
        """
        result = await self.db.execute(
            select(User).where(User.subscription_external_id == preapproval_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            logger.warning(f"No user found for preapproval_id: {preapproval_id}")
            return None

        if action == "preapproval.created":
            tier = plan_id or user.subscription_tier
            user.subscription_tier = tier
            user.subscription_status = status or "active"
            user.subscription_external_id = preapproval_id
            logger.info(f"Subscription created for user {user.id}: {tier}")

        elif action == "preapproval.updated":
            if status:
                user.subscription_status = status
                if status == "cancelled":
                    user.subscription_tier = "free"
                    user.subscription_expires_at = None
            logger.info(f"Subscription updated for user {user.id}: {status}")

        elif action == "preapproval.cancelled":
            user.subscription_tier = "free"
            user.subscription_status = "cancelled"
            user.subscription_expires_at = None
            logger.info(f"Subscription cancelled for user {user.id}")

        await self.db.flush()
        return user
