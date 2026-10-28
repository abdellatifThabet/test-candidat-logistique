import asyncio
import logging
from datetime import timedelta

from sqlalchemy import or_, select

from app.config import get_settings
from app.db.database import SessionLocal
from app.db.models import Order, OrderStatus, utcnow
from app.warehouse.client import deliver_order

logger = logging.getLogger("order-relay.worker")


def _due_order_ids() -> list[str]:
    now = utcnow()
    with SessionLocal() as db:
        stmt = (
            select(Order.id)
            .where(
                Order.status.in_([OrderStatus.PENDING, OrderStatus.RETRYING]),
                or_(Order.next_retry_at.is_(None), Order.next_retry_at <= now),
            )
            .order_by(Order.created_at)
        )
        return list(db.scalars(stmt))


async def _process_order(order_id: str) -> None:
    # Read in a short session so no DB lock is held during the HTTP call.
    with SessionLocal() as db:
        order = db.get(Order, order_id)
        if order is None:
            return
        external_id = order.order_id
        payload = order.payload

    result = await deliver_order(external_id, payload)

    settings = get_settings()
    with SessionLocal() as db:
        order = db.get(Order, order_id)
        if order is None:
            return

        order.attempts += 1

        if result.success:
            order.status = OrderStatus.SENT
            order.last_error = None
            order.next_retry_at = None
            order.warehouse_reference = result.warehouse_reference
        elif result.retryable and order.attempts < settings.max_attempts:
            order.status = OrderStatus.RETRYING
            order.last_error = result.error
            # Exponential backoff: base, base*2, base*4, ...
            delay = settings.retry_base_delay_seconds * (2 ** (order.attempts - 1))
            order.next_retry_at = utcnow() + timedelta(seconds=delay)
        else:
            order.status = OrderStatus.FAILED
            order.last_error = result.error
            order.next_retry_at = None

        db.commit()


async def worker_loop() -> None:
    settings = get_settings()
    while True:
        try:
            for order_id in _due_order_ids():
                await _process_order(order_id)
        except Exception:
            logger.exception("Worker iteration failed")

        await asyncio.sleep(settings.dispatch_interval_seconds)
