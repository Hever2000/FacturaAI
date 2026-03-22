"""Tests for subscription endpoints."""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_plans(client: AsyncClient):
    """Test listing available subscription plans (no auth needed)."""
    response = await client.get("/v1/subscriptions/plans")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2

    plan_ids = [p["id"] for p in data]
    assert "pro" in plan_ids
    assert "enterprise" in plan_ids

    for plan in data:
        assert plan["price"] > 0
        assert plan["currency_id"] == "ARS"
        assert plan["monthly_limit"] > 0
        assert plan["rate_limit_per_minute"] > 0


@pytest.mark.asyncio
async def test_get_current_subscription(
    auth_client: AsyncClient, test_user
):
    """Test getting current subscription status."""
    response = await auth_client.get("/v1/subscriptions/current")
    assert response.status_code == 200
    data = response.json()
    assert data["tier"] == "free"
    assert data["status"] is None
    assert data["monthly_limit"] == 100
    assert data["monthly_remaining"] == 100


@pytest.mark.asyncio
async def test_create_checkout_success(
    auth_client: AsyncClient, test_user
):
    """Test creating a Mercado Pago checkout URL."""
    mock_mp_response = {
        "id": "MP-PREAPPROVAL-123",
        "init_point": "https://www.mercadopago.com.ar/checkout/v1/redirect?preapproval=123",
        "sandbox_init_point": "https://sandbox.mercadopago.com.ar/checkout/v1/redirect?preapproval=123",
    }

    from types import SimpleNamespace

    mock_result = SimpleNamespace(
        preapproval_id="MP-PREAPPROVAL-123",
        init_point=mock_mp_response["init_point"],
        sandbox_init_point=mock_mp_response["sandbox_init_point"],
    )

    with patch(
        "src.services.subscription.SubscriptionService.create_checkout",
        new_callable=AsyncMock,
    ) as mock_checkout:
        mock_checkout.return_value = mock_result

        response = await auth_client.post(
            "/v1/subscriptions/checkout",
            json={"tier": "pro"},
        )

    assert response.status_code == 201
    data = response.json()
    assert data["preapproval_id"] == "MP-PREAPPROVAL-123"
    assert "mercadopago.com" in data["init_point"]


@pytest.mark.asyncio
async def test_create_checkout_invalid_tier(auth_client: AsyncClient):
    """Test checkout fails with invalid tier."""
    response = await auth_client.post(
        "/v1/subscriptions/checkout",
        json={"tier": "platinum"},
    )
    assert response.status_code == 422  # Pydantic validation rejects invalid tier


@pytest.mark.asyncio
async def test_cancel_subscription_no_active(auth_client: AsyncClient, test_user):
    """Test cancelling when no subscription is active."""
    assert test_user.subscription_tier == "free"
    response = await auth_client.post("/v1/subscriptions/cancel")
    assert response.status_code == 400
    assert "No active subscription" in response.json()["detail"]


@pytest.mark.asyncio
async def test_pause_subscription_no_active(auth_client: AsyncClient, test_user):
    """Test pausing when no subscription is active."""
    response = await auth_client.post("/v1/subscriptions/pause")
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_resume_subscription_no_active(auth_client: AsyncClient, test_user):
    """Test resuming when no subscription is active."""
    response = await auth_client.post("/v1/subscriptions/resume")
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_cancel_requires_auth(client: AsyncClient):
    """Test cancel endpoint requires authentication."""
    response = await client.post("/v1/subscriptions/cancel")
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Webhook tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_webhook_disabled_by_default(client: AsyncClient):
    """Test webhook returns 503 when MP is disabled."""
    with patch("src.api.v1.webhooks.settings") as mock_settings:
        mock_settings.MERCADO_PAGO_ENABLED = False

        response = await client.post(
            "/v1/webhooks/mercadopago",
            json={"id": 123, "type": "preapproval", "action": "preapproval.created"},
        )
        assert response.status_code == 503


@pytest.mark.asyncio
async def test_webhook_missing_event_id(client: AsyncClient):
    """Test webhook fails without event id."""
    with patch("src.api.v1.webhooks.settings") as mock_settings:
        mock_settings.MERCADO_PAGO_ENABLED = True
        mock_settings.MERCADO_PAGO_WEBHOOK_SECRET = ""

        response = await client.post(
            "/v1/webhooks/mercadopago",
            json={"type": "preapproval"},
        )
        assert response.status_code == 400
        assert "Missing event id" in response.json()["detail"]


@pytest.mark.asyncio
async def test_webhook_subscription_created(
    client: AsyncClient,
    db_session,
    test_user,
    mock_mp_preapproval_created,
):
    """Test webhook handles preapproval.created."""

    # Set up user with external ID
    test_user.subscription_external_id = "MP-PREAPPROVAL-123"
    await db_session.commit()

    with (
        patch("src.api.v1.webhooks.settings") as mock_settings,
        patch("src.api.v1.webhooks.get_db") as mock_get_db,
        patch("src.api.v1.webhooks.get_redis") as mock_redis,
    ):
        mock_settings.MERCADO_PAGO_ENABLED = True
        mock_settings.MERCADO_PAGO_WEBHOOK_SECRET = ""

        # Mock Redis idempotency check
        mock_redis_instance = AsyncMock()
        mock_redis_instance.exists = AsyncMock(return_value=False)
        mock_redis_instance.setex = AsyncMock()
        mock_redis_instance.set = AsyncMock()
        mock_redis.return_value = mock_redis_instance

        async def mock_get_db_gen():
            yield db_session

        mock_get_db.return_value = mock_get_db_gen()

        response = await client.post(
            "/v1/webhooks/mercadopago",
            json=mock_mp_preapproval_created,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"


# ---------------------------------------------------------------------------
# Rate limit tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_rate_limit_status(auth_client: AsyncClient, test_user):
    """Test getting rate limit status."""
    response = await auth_client.get("/v1/rate-limit/status")
    assert response.status_code == 200
    data = response.json()
    assert "tier" in data
    assert "requests_this_minute" in data
    assert "limit_per_minute" in data
    assert "monthly_usage" in data
    assert "monthly_limit" in data
    assert "monthly_remaining" in data
    assert data["tier"] == "free"
    assert data["monthly_limit"] == 100
