import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db.database import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("order-relay")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()

    # TODO:
    # Start any background processing mechanism you need.
    #
    # You may use FastAPI BackgroundTasks, an asyncio worker, or another
    # simple mechanism, but orders must be persisted before being forwarded
    # and must remain recoverable after a service restart.

    yield

    # TODO: Stop your background worker cleanly if needed.


app = FastAPI(
    title="Reliable Order Relay Service",
    version="1.0.0",
    lifespan=lifespan,
)


# TODO:
# Create your own router(s), for example in `app/api/orders.py`, then include
# them here. The required endpoints are described in the README.


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}