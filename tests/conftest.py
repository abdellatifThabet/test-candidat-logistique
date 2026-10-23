import os
import time
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("WAREHOUSE_BASE_URL", "http://127.0.0.1:9000")
os.environ.setdefault("WAREHOUSE_TIMEOUT_SECONDS", "2")
os.environ.setdefault("MAX_ATTEMPTS", "5")
os.environ.setdefault("RETRY_BASE_DELAY_SECONDS", "0.2")
os.environ.setdefault("DISPATCH_INTERVAL_SECONDS", "0.1")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test_order_relay.db")

from app.main import app  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db.database import init_db  # noqa: E402


@pytest.fixture(scope="session")
def client() -> Callable[[], TestClient]:
    db_path = Path("./test_order_relay.db")
    if db_path.exists():
        db_path.unlink()

    init_db()

    with TestClient(app) as test_client:
        yield lambda: test_client


@pytest.fixture(scope="session")
def warehouse_base_url() -> str:
    return get_settings().warehouse_base_url.rstrip("/")


@pytest.fixture(autouse=True)
def reset_warehouse(warehouse_base_url: str) -> None:
    response = httpx.post(f"{warehouse_base_url}/__test/reset", timeout=5)
    response.raise_for_status()


def wait_for_order_status(
    client: Callable[[], TestClient],
    order_internal_id: str,
    expected_statuses: set[str],
    timeout_seconds: float = 20.0,
) -> dict:
    deadline = time.monotonic() + timeout_seconds
    order: dict = {}

    while time.monotonic() < deadline:
        response = client().get(f"/orders/{order_internal_id}")
        assert response.status_code == 200

        order = response.json()
        if order["status"] in expected_statuses:
            return order

        time.sleep(0.1)

    raise AssertionError(
        f"Order did not reach one of {expected_statuses} within "
        f"{timeout_seconds}s. Last state: {order}"
    )