import uuid

import httpx

from tests.conftest import wait_for_order_status


def make_order_payload(order_id: str) -> dict:
    return {
        "order_id": order_id,
        "customer_id": "CUST-987",
        "items": [
            {
                "sku": "SKU-001",
                "quantity": 2,
            }
        ],
        "shipping_address": {
            "line1": "12 rue des Tests",
            "postal_code": "38000",
            "city": "Grenoble",
            "country": "FR",
        },
    }


def set_warehouse_mode(
    warehouse_base_url: str,
    mode: str,
) -> None:
    response = httpx.post(
        f"{warehouse_base_url}/__test/mode",
        json={"mode": mode},
        timeout=5,
    )
    response.raise_for_status()


def test_health(client):
    response = client().get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_order_is_accepted_and_persisted(client):
    payload = make_order_payload(f"ORD-{uuid.uuid4()}")

    response = client().post("/orders", json=payload)

    assert response.status_code == 202

    body = response.json()
    assert body["order_id"] == payload["order_id"]
    assert body["status"] == "PENDING"
    assert body["attempts"] == 0

    detail = client().get(f"/orders/{body['id']}")
    assert detail.status_code == 200
    assert detail.json()["order_id"] == payload["order_id"]


def test_duplicate_external_order_is_rejected(client):
    payload = make_order_payload("ORD-DUPLICATE-001")

    first = client().post("/orders", json=payload)
    assert first.status_code == 202

    second = client().post("/orders", json=payload)
    assert second.status_code == 409


def test_successful_order_is_forwarded(client, warehouse_base_url):
    set_warehouse_mode(warehouse_base_url, "success")

    payload = make_order_payload(f"ORD-{uuid.uuid4()}")
    created = client().post("/orders", json=payload)
    assert created.status_code == 202

    order = wait_for_order_status(
        client,
        created.json()["id"],
        {"SENT"},
    )

    assert order["attempts"] >= 1
    assert order["last_error"] is None


def test_temporary_server_error_is_retried(client, warehouse_base_url):
    set_warehouse_mode(warehouse_base_url, "server_error")

    payload = make_order_payload(f"ORD-{uuid.uuid4()}")
    created = client().post("/orders", json=payload)
    assert created.status_code == 202

    order = wait_for_order_status(
        client,
        created.json()["id"],
        {"SENT"},
    )

    assert order["attempts"] >= 3


def test_timeout_does_not_lose_order(client, warehouse_base_url):
    set_warehouse_mode(warehouse_base_url, "timeout")

    payload = make_order_payload(f"ORD-{uuid.uuid4()}")
    created = client().post("/orders", json=payload)
    assert created.status_code == 202

    order = wait_for_order_status(
        client,
        created.json()["id"],
        {"RETRYING", "FAILED"},
        timeout_seconds=15,
    )

    assert order["attempts"] >= 1


def test_permanent_failure_is_identifiable(client, warehouse_base_url):
    set_warehouse_mode(warehouse_base_url, "permanent_server_error")

    payload = make_order_payload(f"ORD-{uuid.uuid4()}")
    created = client().post("/orders", json=payload)
    assert created.status_code == 202

    order = wait_for_order_status(
        client,
        created.json()["id"],
        {"FAILED"},
        timeout_seconds=30,
    )

    assert order["attempts"] == 5
    assert order["last_error"] is not None