import asyncio
import os
import uuid
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel

app = FastAPI(
    title="Warehouse System Mock",
    version="1.0.0",
    docs_url="/warehouse/docs",
    redoc_url=None,
)

FailureMode = Literal[
    "success",
    "timeout",
    "server_error",
    "permanent_server_error",
    "flaky",
    "duplicate",
]

FAILURE_MODE = os.getenv("WAREHOUSE_FAILURE_MODE", "success")
SERVER_ERROR_FAILURES_BEFORE_SUCCESS = 2

processed_orders: dict[str, dict] = {}
failure_mode: FailureMode = FAILURE_MODE  # type: ignore[assignment]
server_error_count: dict[str, int] = {}


class TestModeRequest(BaseModel):
    mode: FailureMode


class WarehouseOrderRequest(BaseModel):
    order_id: str
    customer_id: str
    items: list[dict]
    shipping_address: dict


@app.post("/__test/mode")
async def set_test_mode(payload: TestModeRequest) -> dict[str, str]:
    global failure_mode
    failure_mode = payload.mode
    return {"mode": failure_mode}


@app.post("/__test/reset")
async def reset_test_state() -> dict[str, str]:
    global failure_mode
    processed_orders.clear()
    server_error_count.clear()
    failure_mode = os.getenv("WAREHOUSE_FAILURE_MODE", "success")
    return {"status": "reset"}


@app.get("/warehouse/orders/{idempotency_key}")
async def get_order(idempotency_key: str) -> dict:
    order = processed_orders.get(idempotency_key)
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found.",
        )
    return order


@app.post("/warehouse/orders", status_code=status.HTTP_201_CREATED)
async def receive_order(
    payload: WarehouseOrderRequest,
    idempotency_key: str | None = Header(default=None),
    x_test_failure: str | None = Header(default=None),
) -> dict:
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is required.",
        )

    if idempotency_key in processed_orders:
        existing = processed_orders[idempotency_key]

        if failure_mode == "duplicate":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Order has already been processed.",
            )

        return existing

    mode = x_test_failure or failure_mode

    if mode == "timeout":
        await asyncio.sleep(10)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Simulated Warehouse timeout.",
        )

    if mode == "server_error":
        failures = server_error_count.get(idempotency_key, 0)
        if failures < SERVER_ERROR_FAILURES_BEFORE_SUCCESS:
            server_error_count[idempotency_key] = failures + 1
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Simulated temporary Warehouse failure.",
            )

    if mode == "permanent_server_error":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Simulated permanent Warehouse failure.",
        )

    if mode == "flaky":
        if uuid.uuid4().int % 2 == 0:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Simulated intermittent Warehouse failure.",
            )

    warehouse_reference = f"WH-{uuid.uuid4()}"
    response = {
        "warehouse_reference": warehouse_reference,
        "order_id": payload.order_id,
        "status": "ACCEPTED",
    }

    processed_orders[idempotency_key] = response
    return response