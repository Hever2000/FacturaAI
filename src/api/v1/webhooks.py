import hashlib
import hmac
import logging
from datetime import timedelta

from fastapi import APIRouter, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.db import get_db
from src.db.redis import get_redis
from src.services.subscription import SubscriptionService

logger = logging.getLogger("facturaai")

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


async def get_db_session():
    """Get a database session for webhook processing."""
    async for session in get_db():
        yield session


def validate_signature(
    secret: str,
    signature_header: str,
    request_id: str,
    timestamp: str,
    data_id: str,
) -> bool:
    """
    Validate Mercado Pago webhook signature using HMAC SHA256.

    Template: id:{data_id};request-id:{request_id};ts:{timestamp};
    """
    template = f"id:{data_id};request-id:{request_id};ts:{timestamp};"
    expected = hmac.new(
        secret.encode(),
        template.encode(),
        hashlib.sha256,
    ).hexdigest()

    # Parse signature_header: "ts=xxx,v1=xxx"
    received_hash = None
    for part in signature_header.split(","):
        if part.startswith("v1="):
            received_hash = part.split("=", 1)[1].strip()
            break

    if not received_hash:
        return False

    return hmac.compare_digest(expected, received_hash)


async def check_webhook_idempotency(event_id: str) -> bool:
    """
    Check if webhook event was already processed.
    Returns True if already processed (skip), False if new (process).
    """
    redis_client = await get_redis()
    key = f"mp_webhook:{event_id}"
    exists = await redis_client.exists(key)
    if exists:
        logger.info(f"Webhook event {event_id} already processed, skipping")
        return True

    # Mark as processed for 24 hours
    await redis_client.setex(key, timedelta(hours=24), "1")
    return False


def extract_webhook_data(body: dict) -> tuple[str, str, str | None]:
    """
    Extract topic, action, and data.id from webhook body.

    Returns: (topic, action, data_id)
    """
    topic = body.get("type", "")
    action = body.get("action", "")
    data_id = None

    data = body.get("data", {})
    if isinstance(data, dict):
        data_id = data.get("id")

    return topic, action, data_id


async def process_webhook(
    topic: str,
    action: str,
    data_id: str,
    db: AsyncSession,
) -> None:
    """Process a webhook notification."""
    if topic == "preapproval":
        service = SubscriptionService(db)

        if action == "preapproval.created":
            await service.update_user_from_webhook(
                preapproval_id=data_id,
                action="preapproval.created",
                status="authorized",
            )

        elif action in ("preapproval.updated", "preapproval.cancelled", "preapproval.paused"):
            # Get current status from MP
            from src.services.mercadopago import get_mercadopago_client

            client = get_mercadopago_client()
            try:
                mp_data = await client.get_preapproval(data_id)
                mp_status = mp_data.get("status")
                await service.update_user_from_webhook(
                    preapproval_id=data_id,
                    action=action,
                    status=mp_status,
                )
            except Exception as e:
                logger.error(f"Failed to get MP preapproval {data_id}: {e}")
                await service.update_user_from_webhook(
                    preapproval_id=data_id,
                    action=action,
                    status=action.split(".")[-1] if "." in action else None,
                )

    elif topic == "subscription_authorized_payment":
        # Payment received — just log, MP handles retry logic
        logger.info(f"Subscription payment received: {data_id}")

    else:
        logger.info(f"Unhandled webhook topic: {topic} / {action}")


@router.post("/mercadopago")
async def mercadopago_webhook(
    request: Request,
    x_signature: str | None = Header(None),
    x_request_id: str | None = Header(None),
    x_transmission_id: str | None = Header(None),
):
    """
    Mercado Pago webhook endpoint.

    Handles subscription lifecycle events:
    - preapproval.created → activate subscription
    - preapproval.updated → update status
    - preapproval.cancelled → downgrade to free
    - subscription_authorized_payment → log payment
    """
    if not settings.MERCADO_PAGO_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Mercado Pago integration is disabled",
        )

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON body",
        )

    event_id = body.get("id")
    if not event_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing event id",
        )

    # Idempotency check
    if await check_webhook_idempotency(str(event_id)):
        return {"status": "already_processed"}

    # Signature validation (skip in development if no secret configured)
    if settings.MERCADO_PAGO_WEBHOOK_SECRET and x_signature:
        timestamp = ""
        # Try to extract from x-signature header
        if x_signature:
            for part in x_signature.split(","):
                if part.startswith("ts="):
                    timestamp = part.split("=", 1)[1].strip()
                    break

        data_id = body.get("data", {}).get("id", "")
        request_id = x_request_id or ""

        if not validate_signature(
            secret=settings.MERCADO_PAGO_WEBHOOK_SECRET,
            signature_header=x_signature,
            request_id=request_id,
            timestamp=timestamp,
            data_id=data_id,
        ):
            logger.warning(f"Invalid webhook signature for event {event_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid signature",
            )

    topic, action, data_id = extract_webhook_data(body)

    if not data_id:
        logger.warning(f"Missing data.id in webhook body: {event_id}")
        return {"status": "ok"}

    # Process in a separate task to return 200 quickly
    # We need to create our own db session for processing
    async for db in get_db():
        try:
            await process_webhook(topic, action, data_id, db)
            await db.commit()
        except Exception as e:
            logger.error(f"Webhook processing error for {event_id}: {e}")
            await db.rollback()
        break

    return {"status": "ok"}
