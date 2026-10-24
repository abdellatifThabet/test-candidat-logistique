# Paid Technical Test — Reliable Order Relay Service

## Context

You will build a small service that reliably transfers orders from a fictional
Order Management System (OMS) to an external Warehouse System.

The Warehouse API is already provided as a simulated external service. It may
fail, time out, return server errors, or receive duplicate requests.

Your service must ensure that:

- No order is lost.
- No order is forwarded twice in a way that creates a duplicate warehouse operation.
- Failures are visible, traceable and recoverable.
- The service can be restarted without losing pending work.

```text
Order Management System (fictional)
              |
              v
   Your Order Relay Service  <-- You implement this
              |
              v
     Warehouse System (mock provided)
```

## Your task

Implement the Order Relay Service using the provided FastAPI base project.

Your service must:

1. Receive orders through an HTTP API.
2. Validate and persist incoming orders before attempting to forward them.
3. Forward orders to the provided Warehouse mock.
4. Handle network errors, timeouts and HTTP 5xx responses.
5. Retry failed deliveries in a controlled way.
6. Prevent duplicate processing of the same external order.
7. Track the processing status and the number of attempts.
8. Make failed orders identifiable and inspectable.
9. Include automated tests for the main success and failure scenarios.
10. Explain your technical decisions in a short `CANDIDATE_NOTES.md`.

You are not asked to build a production-ready distributed system. We value a
simple, readable and well-reasoned solution over unnecessary complexity.

## Time expected

You have up to **3 hours**.

AI-assisted development tools are allowed. However, you must be able to explain
and defend every part of your implementation.

## Technical constraints

Use the stack provided in the repository:

- Python 3.11+
- FastAPI
- SQLAlchemy
- SQLite
- httpx
- pytest

Do **not** add Redis, Celery, RabbitMQ, Docker, PostgreSQL, Alembic or any other
infrastructure unless you consider it essential. If you believe one of these
would be useful in production, explain it in `CANDIDATE_NOTES.md` instead of
implementing it.

## What is provided

This repository provides only the non-business foundation:

- FastAPI application entry point.
- SQLite database setup.
- Configuration through `.env`.
- A simulated Warehouse API.
- Contract tests.
- CI workflow.

You must design and implement the Order Relay Service yourself, including:

- API endpoints.
- Pydantic schemas.
- SQLAlchemy models.
- Database persistence.
- Warehouse HTTP client.
- Order processing.
- Retry and idempotency logic.
- Your own tests.

You are free to choose your internal file structure. The existing `app/api/`,
`app/services/` and `app/warehouse/` packages are suggestions, not requirements.

## Repository rules

You must not modify:

- `warehouse_mock/`
- `tests/contract/`
- `.github/workflows/ci.yml`

You may add files and folders elsewhere in the repository.

You must implement your own tests in:

```text
tests/candidate/
```

The tests in `tests/contract/` validate the minimum expected behaviour. They are
not exhaustive: you are expected to add your own tests for edge cases and
failure scenarios.

## Required order statuses

Your service must expose and persist the following statuses:

| Status | Meaning |
|---|---|
| `PENDING` | Order has been received and persisted, but not yet forwarded |
| `PROCESSING` | Optional: order is currently being forwarded |
| `SENT` | Warehouse accepted the order |
| `RETRYING` | A retryable failure occurred; another attempt is scheduled |
| `FAILED` | Maximum attempts reached, or a non-retryable error occurred |

`PENDING`, `SENT`, `RETRYING` and `FAILED` are required. `PROCESSING` is optional.


## Getting started

### 1. Clone the repository

```bash
git clone https://github.com/movanex/test-candidat-logistique.git
cd test-candidat-logistique
```

### 2. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

On Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure the environment

Copy the example environment file:

```bash
cp .env.example .env
```

The default values work locally. You normally do not need to change them.

| Variable | Default | Description |
|---|---|---|
| `WAREHOUSE_BASE_URL` | `http://127.0.0.1:9000` | Base URL of the Warehouse mock |
| `WAREHOUSE_FAILURE_MODE` | `success` | Failure mode used by the Warehouse mock |
| `WAREHOUSE_TIMEOUT_SECONDS` | `3` | Timeout for calls to the Warehouse |
| `MAX_ATTEMPTS` | `5` | Maximum number of delivery attempts |
| `DATABASE_URL` | `sqlite:///./order_relay.db` | Local SQLite database |

### 5. Start the Warehouse mock

In a first terminal:

```bash
uvicorn warehouse_mock.main:app --reload --port 9000
```

The Warehouse mock is available at:

```text
http://127.0.0.1:9000
```

### 6. Start your Order Relay Service

In a second terminal:

```bash
uvicorn app.main:app --reload --port 8000
```

Your service must be available at:

```text
http://127.0.0.1:8000
```

FastAPI documentation will be available at:

```text
http://127.0.0.1:8000/docs
```

## Warehouse mock

The public Warehouse endpoint is:

```http
POST /warehouse/orders
```

It expects a JSON payload and an idempotency header:

```http
Idempotency-Key: <stable-order-identifier>
```

The following endpoints are for test orchestration only:

- `POST /__test/mode`
- `POST /__test/reset`
- `GET /warehouse/orders/{idempotency_key}`

You must not call the test endpoints from production code. They are used by the
provided contract tests and can be used locally to simulate failures.


The Warehouse mock supports the following failure modes:

| Mode | Behaviour |
|---|---|
| `success` | Always returns a successful response |
| `timeout` | Delays its response beyond the configured client timeout |
| `server_error` | Returns HTTP 500 before eventually succeeding |
| `flaky` | Fails intermittently |
| `duplicate` | Rejects a repeated delivery for the same idempotency key |
| `permanent_server_error` | Always returns HTTP 500 |

You can change the default failure mode in `.env`:

```env
WAREHOUSE_FAILURE_MODE=server_error
```

You may also use the following test header when calling the Warehouse mock
directly during local manual testing:

```http
X-Test-Failure: timeout
```

Your Order Relay Service does **not** need to forward this header. The provided
contract tests change the Warehouse failure mode through `POST /__test/mode`.

Possible values:

```text
success
timeout
server_error
permanent_server_error
flaky
duplicate
```

Do not modify the Warehouse mock. Treat it as an external system that you cannot
control.

## API to implement

### Receive an order

```http
POST /orders
```

Example request:

```json
{
  "order_id": "ORD-12345",
  "customer_id": "CUST-987",
  "items": [
    {
      "sku": "SKU-001",
      "quantity": 2
    }
  ],
  "shipping_address": {
    "line1": "12 rue des Tests",
    "postal_code": "38000",
    "city": "Grenoble",
    "country": "FR"
  }
}
```

Expected behaviour:

- Validate the payload.
- Persist the order before calling the Warehouse.
- Return a response indicating that the order has been accepted for processing.
- Forward the order to the Warehouse asynchronously or through a background worker.
- Use a stable identifier when calling the Warehouse so that retries do not create duplicates.

Required response:

```json
{
  "id": "b3b24c58-4a83-4d61-9f3f-2f0f9e8d1a77",
  "order_id": "ORD-12345",
  "status": "PENDING",
  "attempts": 0
}
```

The response must include at least these fields:

- `id`: internal order identifier.
- `order_id`: external order identifier received from the OMS.
- `status`: current processing status.
- `attempts`: number of delivery attempts already made.

`GET /orders/{id}` must also expose `last_error`. It may expose additional
fields, such as `warehouse_reference`.

A status code such as `202 Accepted` is appropriate if forwarding is asynchronous.

If an order with the same `order_id` has already been received, return:

```http
409 Conflict
```

The service must not create a second persisted order or schedule a second
Warehouse delivery for that order.

### Inspect an order

```http
GET /orders/{id}
```

The response must allow us to understand:

- The current processing status.
- The number of attempts.
- The last error, if any.
- The Warehouse response or reference, if available.

### List failed orders

```http
GET /orders?status=FAILED
```

This endpoint is optional but recommended. It should make failed operations easy
to identify.

### Retry a failed order

```http
POST /orders/{id}/retry
```

This endpoint is optional but recommended. It should allow a failed order to be
queued again for processing.

## Database requirements

Use SQLite and create the tables with SQLAlchemy’s `create_all()`.

You must design the persistence model yourself. At minimum, it must allow the
service to store:

- An internal identifier.
- The external order identifier.
- The full order payload.
- The current processing status.
- The number of delivery attempts.
- The next retry time, if applicable.
- The last error message.
- The Warehouse response or reference, if available.
- Creation and update timestamps.

A same external order must not be persisted twice.

In `CANDIDATE_NOTES.md`, include the SQL schema corresponding to your SQLAlchemy
models. This helps us assess your understanding of the underlying database
design.

Example:

```sql
CREATE TABLE orders (
    ...
);
```

## Reliability requirements

Your implementation should clearly handle at least the following cases:

| Scenario | Expected behaviour |
|---|---|
| Warehouse returns success | Order is marked as successfully forwarded |
| Warehouse times out | Order is not lost; a retry is scheduled |
| Warehouse returns HTTP 500 | Order is not lost; a retry is scheduled |
| Warehouse returns HTTP 4xx | Order is marked as failed, unless the error is retryable |
| Same order is received twice | No duplicate warehouse delivery is created |
| Maximum retries reached | Order is identifiable as failed, with the last error stored |
| Service restarts | Pending or retryable orders can be processed again |

Think carefully about the timeout case: a timeout does not necessarily mean that
the Warehouse did not receive or process the order.

## Tests

The contract tests communicate with the Warehouse mock over HTTP. Therefore,
start the Warehouse mock before running them:

```bash
uvicorn warehouse_mock.main:app --port 9000
```

### Run all tests

```bash
pytest
```

### Run only the provided contract tests

```bash
pytest tests/contract
```

### Run only your tests

```bash
pytest tests/candidate
```

You must add tests in `tests/candidate/` covering at least:

- Successful forwarding.
- Timeout handling.
- HTTP 500 handling.
- Duplicate order reception.
- Retry exhaustion.
- Persistence of failure information.

Use `pytest` and the FastAPI `TestClient`, or `httpx` if you prefer asynchronous
tests. The provided contract tests show the expected style and fixtures.

## Git workflow

1. Clone the repository.
2. Create a feature branch:

```bash
git checkout -b feature/order-relay
```

3. Commit regularly with clear messages.
4. Push your branch to GitHub.
5. Open a pull request targeting `main`.
6. Wait for CI to pass.
7. Merge your pull request once CI is green.

## Deliverables

Your pull request must include:

- A working Order Relay Service.
- SQLAlchemy models and database creation.
- API endpoints described above.
- Communication with the Warehouse mock.
- Failure, timeout and retry handling.
- Duplicate protection.
- Your own automated tests in `tests/candidate/`.
- A `CANDIDATE_NOTES.md` file.

## CANDIDATE_NOTES.md

Create a short document explaining:

1. How to run your solution.
2. Your database design and why.
3. Your order lifecycle and status transitions.
4. How retries work.
5. How you prevent duplicate processing.
6. How you handle the timeout ambiguity.
7. What you would improve for production.
8. Any assumption you made.

Keep it concise: around 1 to 2 pages is enough.

## Evaluation criteria

| Criterion | What we assess |
|---|---|
| Reliability | Orders are neither lost nor duplicated |
| Database design | Appropriate fields, constraints, statuses and traceability |
| FastAPI | Clean endpoints, validation and project organisation |
| API integration | Correct HTTP client usage, timeouts and response handling |
| Resilience | Controlled retries, idempotence and recovery |
| Testing | Relevant success, failure and duplicate scenarios |
| Git | Clear branch, commits and pull request |
| Reasoning | Ability to explain and defend your technical choices |

## Out of scope

You do not need to implement:

- Authentication or authorization.
- Docker.
- Kubernetes.
- Redis, Celery or RabbitMQ.
- PostgreSQL.
- Advanced observability.
- A frontend.
- Real cloud deployment.

Cloud deployment, including Azure, is optional and will not be required to
complete the test.

## Questions

If something is ambiguous, make a reasonable assumption, document it in
`CANDIDATE_NOTES.md`, and continue. Do not spend excessive time waiting for
clarification.
