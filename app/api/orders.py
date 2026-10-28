from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas import OrderAcceptedResponse, OrderCreate, OrderResponse
from app.db.database import get_db
from app.db.models import Order, OrderStatus

router = APIRouter(prefix="/orders", tags=["orders"])


def _get_order_or_404(db: Session, order_id: str) -> Order:
    order = db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


def _list_orders(db: Session, status_filter: OrderStatus | None = None) -> list[Order]:
    stmt = select(Order).order_by(Order.created_at)
    if status_filter is not None:
        stmt = stmt.where(Order.status == status_filter)
    return list(db.scalars(stmt))


# Static route must come before /{order_id}.
@router.get("/failed", response_model=list[OrderResponse])
def list_failed_orders(db: Session = Depends(get_db)):
    return _list_orders(db, OrderStatus.FAILED)


@router.get("", response_model=list[OrderResponse])
def list_orders(
    status_filter: OrderStatus | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
):
    return _list_orders(db, status_filter)


@router.post("", response_model=OrderAcceptedResponse, status_code=http_status.HTTP_202_ACCEPTED)
def create_order(payload: OrderCreate, db: Session = Depends(get_db)):
    if db.scalar(select(Order.id).where(Order.order_id == payload.order_id)):
        raise HTTPException(status_code=409, detail="Order already exists")

    order = Order(
        order_id=payload.order_id,
        payload=payload.model_dump(),
        status=OrderStatus.PENDING,
        attempts=0,
    )
    db.add(order)

    # The unique constraint is the final guard against concurrent duplicates.
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Order already exists")

    return order


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(order_id: str, db: Session = Depends(get_db)):
    return _get_order_or_404(db, order_id)


@router.post("/{order_id}/retry", response_model=OrderResponse)
def retry_order(order_id: str, db: Session = Depends(get_db)):
    order = _get_order_or_404(db, order_id)
    if order.status != OrderStatus.FAILED:
        raise HTTPException(status_code=409, detail="Only failed orders can be retried")

    order.status = OrderStatus.PENDING
    order.attempts = 0
    order.next_retry_at = None
    order.last_error = None
    db.commit()
    return order
