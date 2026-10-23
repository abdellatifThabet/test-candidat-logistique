"""
TODO: Create the SQLAlchemy model(s) required by the Order Relay Service.

Requirements:
- Store the external order ID and prevent duplicate external orders.
- Store the original order payload.
- Track the processing status.
- Track delivery attempts.
- Store the last error.
- Store the Warehouse response/reference when available.
- Store creation and update timestamps.
- Support retry scheduling.

Do not modify `app/db/database.py`.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# TODO: Define your Order model here.