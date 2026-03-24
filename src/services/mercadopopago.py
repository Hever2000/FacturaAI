import logging
from typing import Any

import httpx

from src.core.config import settings

logger = logging.getLogger("facturaai")

BASE_URL = "https://api.mercadopago.com"


class MercadoPagoError(Exception):
    """Exception raised when Mercado Pago API returns an error."""

    def __init__(self, message: str, status_code: int | None = None, response: dict | None = None):
        self.message = message
        self.status_code = status_code
        self.response = response or {}
        super().__init__(self.message)


class MercadoPagoClient:
    """Async client for Mercado Pago API."""

    def __init__(self, access_token: str | None = None):
        self.access_token = access_token or settings.MERCADO_PAGO_ACCESS_TOKEN
        self.base_url = BASE_URL
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: dict | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated request to Mercado Pago API."""
        client = await self._get_client()

        headers: dict[str, str] = {}
        if idempotency_key:
            headers["X-Idempotency-Key"] = idempotency_key

        try:
            response = await client.request(
                method=method,
                url=endpoint,
                json=data,
                headers=headers if headers else None,
            )

            if response.status_code >= 400:
                logger.error(f"MP API error: {response.status_code} - {response.text}")
                raise MercadoPagoError(
                    message=f"MP API error: {response.status_code}",
                    status_code=response.status_code,
                    response=response.json() if response.text else {},
                )

            return response.json()

        except httpx.HTTPError as e:
            logger.error(f"MP HTTP error: {e}")
            raise MercadoPagoError(message=f"HTTP error: {str(e)}")

    async def create_preapproval(
        self,
        tier: str,
        payer_email: str,
        reason: str,
        back_url: str,
    ) -> dict[str, Any]:
        """
        Create a preapproval (subscription) in Mercado Pago.

        Returns MP response with id, init_point, sandbox_init_point.
        """
        prices: dict[str, float] = {
            "pro": 1500.0,
            "enterprise": 4500.0,
        }
        price = prices.get(tier, 0)

        data = {
            "reason": reason,
            "payer_email": payer_email,
            "auto_recurring": {
                "frequency": 1,
                "frequency_type": "months",
                "transaction_amount": price,
                "currency_id": "ARS",
            },
            "back_url": back_url,
            "status": "pending",
        }

        return await self._request(
            method="POST",
            endpoint="/preapproval",
            data=data,
            idempotency_key=f"preapproval-{tier}-{payer_email}",
        )

    async def update_preapproval(
        self,
        preapproval_id: str,
        status: str | None = None,
        auto_recurring: dict | None = None,
    ) -> dict[str, Any]:
        """
        Update a preapproval (pause, resume, cancel).

        status: "paused", "authorized", "cancelled"
        """
        data: dict[str, Any] = {}
        if status:
            data["status"] = status
        if auto_recurring:
            data["auto_recurring"] = auto_recurring

        return await self._request(
            method="PUT",
            endpoint=f"/preapproval/{preapproval_id}",
            data=data,
            idempotency_key=f"update-{preapproval_id}-{status}",
        )

    async def get_preapproval(self, preapproval_id: str) -> dict[str, Any]:
        """Get preapproval details from Mercado Pago."""
        return await self._request(
            method="GET",
            endpoint=f"/preapproval/{preapproval_id}",
        )


# Singleton instance
_mp_client: MercadoPagoClient | None = None


def get_mercadopago_client() -> MercadoPagoClient:
    """Get or create Mercado Pago client singleton."""
    global _mp_client
    if _mp_client is None:
        _mp_client = MercadoPagoClient()
    return _mp_client
