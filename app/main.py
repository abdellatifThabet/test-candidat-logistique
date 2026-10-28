import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.api.orders import router as orders_router
from app.db.database import init_db
from app.services.worker import worker_loop

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("order-relay")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    # The worker polls the DB, so pending work resumes after a restart.
    worker = asyncio.create_task(worker_loop())

    yield

    worker.cancel()
    with suppress(asyncio.CancelledError):
        await worker


app = FastAPI(
    title="Reliable Order Relay Service",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(orders_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
