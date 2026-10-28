from pydantic import BaseModel, ConfigDict, Field

from app.db.models import OrderStatus


class ItemCreate(BaseModel):
    sku: str = Field(min_length=1)
    quantity: int = Field(gt=0)


class AddressCreate(BaseModel):
    line1: str = Field(min_length=1)
    postal_code: str = Field(min_length=1)
    city: str = Field(min_length=1)
    country: str = Field(min_length=1)


class OrderCreate(BaseModel):
    order_id: str = Field(min_length=1, max_length=255)
    customer_id: str = Field(min_length=1)
    items: list[ItemCreate] = Field(min_length=1)
    shipping_address: AddressCreate


class OrderAcceptedResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    order_id: str
    status: OrderStatus
    attempts: int


class OrderResponse(OrderAcceptedResponse):
    last_error: str | None = None
    warehouse_reference: str | None = None
