# Candidate Notes — Order Relay Service

## How to run

See the **Getting started** and **Tests** sections of `README.md`.

In short: start the Warehouse mock on port 9000, start the relay on port 8000,
then run `pytest` with the mock still running.

## Database design

One table is enough: each external order needs one row, not a full attempt
history.

- `id`: internal UUID returned by the API.
- `order_id`: external OMS identifier; the unique index is the duplicate guard.
- `payload`: original JSON, replayed unchanged after a restart.
- `status`, `attempts`, `next_retry_at`: persisted so retries survive restarts.
- `last_error`, `warehouse_reference`: make failures and successes inspectable.
- `created_at`, `updated_at`: ordering and traceability.

Indexes are deliberate:

- `ix_orders_order_id` (unique): duplicate detection and fast lookup on `POST`.
- `ix_orders_status`: failed-order listing and worker filtering.
- `ix_orders_next_retry_at`: the worker finds due retries without a full scan.

On SQLite these are cheap; the unique index is also a correctness constraint.

Equivalent SQL:

```sql
CREATE TABLE orders (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    order_id VARCHAR(255) NOT NULL,
    payload JSON NOT NULL,
    status VARCHAR(8) NOT NULL,
    attempts INTEGER NOT NULL,
    next_retry_at DATETIME,
    last_error TEXT,
    warehouse_reference VARCHAR(255),
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
);

CREATE UNIQUE INDEX ix_orders_order_id ON orders (order_id);
CREATE INDEX ix_orders_status ON orders (status);
CREATE INDEX ix_orders_next_retry_at ON orders (next_retry_at);
```

`status` is a Python enum stored as a string. SQLAlchemy validates values on
write, and FastAPI/Pydantic rejects invalid filter values.

## Order lifecycle

```text
PENDING --> SENT
PENDING --> RETRYING --> SENT
PENDING --> RETRYING --> RETRYING --> FAILED
PENDING --> FAILED        (non-retryable 4xx)
FAILED  --> PENDING       (manual retry)
```

- `PENDING`: persisted, not yet delivered.
- `RETRYING`: a retryable failure occurred and `next_retry_at` is set.
- `SENT`: the Warehouse accepted the order.
- `FAILED`: max attempts reached, or a non-retryable error occurred.

`PROCESSING` is optional in the README and intentionally unused: an order is
either due (`PENDING`/`RETRYING`) or terminal (`SENT`/`FAILED`). A single worker
prevents double processing, and a crash leaves due work for the next poll.

## How retries work

- Each actual Warehouse call increments `attempts`.
- Timeouts, connection errors, `408`, `429`, and `5xx` are retryable.
- Other `4xx` responses are permanent failures.
- A retryable failure below `MAX_ATTEMPTS` moves the order to `RETRYING` and sets
  `next_retry_at` with exponential backoff:
  `RETRY_BASE_DELAY_SECONDS * 2^(attempts - 1)`.
- Reaching `MAX_ATTEMPTS` moves the order to `FAILED` with the last error stored.
- `POST /orders/{id}/retry` resets a failed order to `PENDING`, including
  `attempts = 0`, so it gets a full new retry cycle.

## Duplicate prevention

Three layers:

1. `POST /orders` checks for an existing `order_id` and returns `409`.
2. The `order_id` unique index makes concurrent inserts fail, so two rows cannot
   be created. The `IntegrityError` is converted to `409`.
3. Every Warehouse call uses the stable `order_id` as `Idempotency-Key`, so a
   retry after a timeout cannot create a second warehouse operation.

## Timeout ambiguity

A timeout does not prove the Warehouse did not receive or process the order. It
may mean:

- the request never arrived,
- it was processed but the response was lost,
- it is still being processed.

The service cannot distinguish these cases. It therefore retries with the same
idempotency key. The Warehouse returns the previously stored result, or `409` if
it already has the key. A `409` is treated as success because the operation
already exists.

The same reasoning covers a crash after Warehouse success but before the DB
commit: on restart the order is retried, the Warehouse recognises the key, and
the order is marked `SENT`.

## Restart recovery

There is no in-memory queue. The SQLite database is the queue. On startup,
`lifespan` creates the worker task; the worker queries orders where:

```text
status IN (PENDING, RETRYING)
AND (next_retry_at IS NULL OR next_retry_at <= now)
```

`PENDING` orders resume immediately. `RETRYING` orders resume when their
scheduled retry time is due. The saved `attempts` value means the backoff
continues from where it stopped.

## Inspection endpoints

- `GET /orders/{id}`: current status, attempts, last error, warehouse reference.
- `GET /orders?status=FAILED`: flexible status filter.
- `GET /orders/failed`: convenience endpoint required by the CI workflow.
- `POST /orders/{id}/retry`: requeue a failed order.

## Verified scenarios

Manual runs (results are in `order_relay.db`):

| Scenario | Observed |
|---|---|
| Success | `SENT`, attempts 1 |
| Timeout | `RETRYING` while attempts remain, then `FAILED` at 5 |
| Temporary `500` | `SENT`, attempts 3 |
| Permanent `500` | `FAILED`, attempts 5, `last_error` set |
| Duplicate `POST` | `409`, one row only |
| Flaky | retried and eventually `SENT` |

## What I would improve for production

- Keep the DB as the queue for this scope. If throughput grows, Redis + `arq`
  fits FastAPI's asyncio model; Celery is unnecessary here because forwarding is
  I/O-bound HTTP, not CPU-bound work. Celery suits Django/heavy jobs, but adds a
  heavier worker stack. 
- Move to PostgreSQL before running several relay instances. SQLite allows one
  writer, while Postgres supports `SELECT ... FOR UPDATE SKIP LOCKED` so workers
  claim orders atomically without double delivery.
- Keep a separate attempt-history table for full auditability.
- Use Alembic migrations instead of `create_all()`.
- Add structured logs, metrics, and alerting for failures and retry rates.
- Add authentication, request tracing, and rate limiting.
- Add CI quality gates: Ruff for linting and formatting (fast, one tool instead
  of flake8/isort/black), plus dependency and security scans (`pip-audit`,
  `bandit`). Optionally add Docker/Compose for reproducible local runs;

These are intentionally not implemented: the task asks for a simple, readable
solution and explicitly discourages extra infrastructure.

## Assumptions

- A `409` from the Warehouse means "already processed", so the order is marked
  `SENT`.
- A manual retry starts a new attempt cycle, so `attempts` is reset to `0`.
- The external `order_id` is the correct idempotency key.
- A single service instance and a single worker are sufficient.
- No authentication or multi-tenancy is required.
