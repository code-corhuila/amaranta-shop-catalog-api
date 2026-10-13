"""The two INTERNAL endpoints Sales calls (spec DP-8, section 8.5, step 3).

The gateway never publishes /internal: only the services on the platform network can reach it, which is why these
routes ask for no token (spec OD-3, upgradable to a shared-secret header the day anything is exposed).
"""

import uuid

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from catalog.application.port.inbound.stock import ReleaseStock, ReserveStock, StockItem


class ItemBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: uuid.UUID = Field(alias="productId")
    quantity: StrictInt = Field(ge=1)   # StrictInt: 1.5 and "2" are refused instead of becoming 1 and 2


class ReserveBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[ItemBody] = Field(min_length=1)


class ReleaseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[ItemBody]


def _stock_items(body) -> list[StockItem]:
    return [StockItem(str(i.product_id), i.quantity) for i in body.items]


def internal_router(reserve: ReserveStock, release: ReleaseStock) -> APIRouter:
    router = APIRouter(prefix="/internal/products")

    @router.post("/reserve-stock")
    def reserve_stock(body: ReserveBody) -> dict:
        lines = reserve.execute(_stock_items(body))
        return {"lines": [{"productId": l.product_id, "productName": l.product_name, "unitPriceAmount": l.unit_price_amount,
                           "quantity": l.quantity} for l in lines]}

    @router.post("/release-stock", status_code=204)
    def release_stock(body: ReleaseBody) -> Response:
        release.execute(_stock_items(body))
        return Response(status_code=204)

    return router
