from dataclasses import dataclass

import httpx

from app.config import get_settings


@dataclass
class DeliveryResult:
    success: bool
    retryable: bool = False
    error: str | None = None
    warehouse_reference: str | None = None


async def deliver_order(order_id: str, payload: dict) -> DeliveryResult:
    settings = get_settings()
    url = f"{settings.warehouse_base_url.rstrip('/')}/warehouse/orders"

    try:
        async with httpx.AsyncClient(
            timeout=settings.warehouse_timeout_seconds
        ) as client:
            response = await client.post(
                url,
                json=payload,
                headers={"Idempotency-Key": order_id},
            )
    except httpx.TimeoutException:
        return DeliveryResult(
            success=False, retryable=True, error="Warehouse request timed out"
        )
    except httpx.RequestError as exc:
        return DeliveryResult(
            success=False, retryable=True, error=f"Warehouse request failed: {exc}"
        )

    if response.is_success:
        try:
            body = response.json()
            reference = (
                body.get("warehouse_reference") if isinstance(body, dict) else None
            )
        except ValueError:
            reference = None
        return DeliveryResult(success=True, warehouse_reference=reference)

    error = f"HTTP {response.status_code}: {response.text[:200]}"

    # 409 means this idempotency key was already processed.
    if response.status_code == 409:
        return DeliveryResult(success=True)

    if response.status_code in (408, 429) or response.status_code >= 500:
        return DeliveryResult(success=False, retryable=True, error=error)

    return DeliveryResult(success=False, retryable=False, error=error)
