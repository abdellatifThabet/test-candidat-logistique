import uuid

import httpx

from tests.conftest import wait_for_order_status


def make_order(order_id: str) -> dict:
    return {
        "order_id": order_id,
        "customer_id": "CUST-987",
        "items": [{"sku": "SKU-001", "quantity": 2}],
        "shipping_address": {
            "line1": "12 rue des Tests",
            "postal_code": "38000",
            "city": "Grenoble",
            "country": "FR",
        },
    }


def new_order_id() -> str:
    return f"ORD-{uuid.uuid4()}"


def set_warehouse_mode(base_url: str, mode: str) -> None:
    response = httpx.post(f"{base_url}/__test/mode", json={"mode": mode}, timeout=5)
    response.raise_for_status()


def test_successful_forwarding(client, warehouse_base_url):
    set_warehouse_mode(warehouse_base_url, "success")
    created = client().post("/orders", json=make_order(new_order_id()))
    assert created.status_code == 202

    order = wait_for_order_status(client, created.json()["id"], {"SENT"})
    assert order["attempts"] >= 1
    assert order["last_error"] is None
    assert order["warehouse_reference"] is not None


def test_timeout_is_retried(client, warehouse_base_url):
    set_warehouse_mode(warehouse_base_url, "timeout")
    created = client().post("/orders", json=make_order(new_order_id()))
    assert created.status_code == 202

    order = wait_for_order_status(
        client,
        created.json()["id"],
        {"RETRYING", "FAILED"},
        timeout_seconds=15,
    )
    assert order["attempts"] >= 1
    assert order["last_error"] is not None


def test_server_error_is_retried(client, warehouse_base_url):
    set_warehouse_mode(warehouse_base_url, "server_error")
    created = client().post("/orders", json=make_order(new_order_id()))
    assert created.status_code == 202

    order = wait_for_order_status(client, created.json()["id"], {"SENT"})
    assert order["attempts"] >= 3
    assert order["last_error"] is None


def test_duplicate_order_is_rejected(client):
    order_id = new_order_id()
    first = client().post("/orders", json=make_order(order_id))
    assert first.status_code == 202

    second = client().post("/orders", json=make_order(order_id))
    assert second.status_code == 409


def test_retry_exhaustion_and_failure_info(client, warehouse_base_url):
    set_warehouse_mode(warehouse_base_url, "permanent_server_error")
    created = client().post("/orders", json=make_order(new_order_id()))
    assert created.status_code == 202

    order = wait_for_order_status(
        client,
        created.json()["id"],
        {"FAILED"},
        timeout_seconds=30,
    )
    assert order["attempts"] == 5
    assert order["last_error"]

    detail = client().get(f"/orders/{created.json()['id']}")
    assert detail.status_code == 200
    assert detail.json()["last_error"] == order["last_error"]


def test_failed_list_and_manual_retry(client, warehouse_base_url):
    set_warehouse_mode(warehouse_base_url, "permanent_server_error")
    created = client().post("/orders", json=make_order(new_order_id()))
    order_id = created.json()["id"]

    wait_for_order_status(client, order_id, {"FAILED"}, timeout_seconds=30)

    failed = client().get("/orders/failed")
    assert failed.status_code == 200
    assert any(item["id"] == order_id for item in failed.json())

    filtered = client().get("/orders", params={"status": "FAILED"})
    assert filtered.status_code == 200
    assert any(item["id"] == order_id for item in filtered.json())

    set_warehouse_mode(warehouse_base_url, "success")
    retried = client().post(f"/orders/{order_id}/retry")
    assert retried.status_code == 200
    assert retried.json()["status"] == "PENDING"

    final = wait_for_order_status(client, order_id, {"SENT"})
    assert final["attempts"] >= 1
