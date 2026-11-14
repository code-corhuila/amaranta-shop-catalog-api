"""The administration of the products: ADMIN only. The role is asked at the router, so no route can forget it."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from catalog.adapter.inbound.http.auth import Rs256Verifier, require_role
from catalog.adapter.inbound.http.view import page_view, product_view
from catalog.application.page import MAX_LIMIT
from catalog.application.port.inbound.products import AdminProductPorts, NewProduct, ProductChanges
from catalog.domain.model.category import Category

BASE = "/api/v1/admin/products"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=False)


class CreateBody(Strict):
    sku: str = Field(min_length=2, max_length=50)
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(max_length=500)
    category: Category
    price: StrictInt = Field(ge=1)               # whole pesos: 10.5 is refused instead of becoming 10
    stock_quantity: StrictInt = Field(ge=0, alias="stockQuantity")
    image_url: str = Field(max_length=500, alias="imageUrl")


class UpdateBody(Strict):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    category: Category | None = None
    price: StrictInt | None = Field(default=None, ge=1)
    image_url: str | None = Field(default=None, max_length=500, alias="imageUrl")

    @model_validator(mode="after")
    def at_least_one_field(self):
        if not self.model_fields_set:
            raise ValueError("at least one field to change is required")
        return self


class StockBody(Strict):
    stock_quantity: StrictInt = Field(ge=0, alias="stockQuantity")


def _admin_view(product) -> dict:
    return {**product_view(product), "isActive": product.is_active}


def admin_router(admin: AdminProductPorts, verifier: Rs256Verifier) -> APIRouter:
    router = APIRouter(prefix=BASE, dependencies=[Depends(require_role("ADMIN", verifier=verifier))])

    @router.get("")
    def list_all(page: Annotated[int, Query(ge=1)] = 1, limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 20) -> dict:
        return page_view(admin.list_all.execute(page, limit), _admin_view)

    @router.post("", status_code=201)
    def create(body: CreateBody, response: Response) -> dict:
        product = admin.create.execute(NewProduct(sku=body.sku, name=body.name, description=body.description,
                                                  category=body.category, price=body.price,
                                                  stock_quantity=body.stock_quantity, image_url=body.image_url))
        response.headers["Location"] = f"{BASE}/{product.id}"
        return _admin_view(product)

    @router.patch("/{product_id}")
    def update(product_id: uuid.UUID, body: UpdateBody) -> dict:
        given = {name: getattr(body, name) for name in body.model_fields_set}
        return _admin_view(admin.update.execute(str(product_id), ProductChanges(**given)))

    @router.patch("/{product_id}/stock")
    def set_stock(product_id: uuid.UUID, body: StockBody) -> dict:
        return _admin_view(admin.set_stock.execute(str(product_id), body.stock_quantity))

    @router.post("/{product_id}/activate")
    def activate(product_id: uuid.UUID) -> dict:
        return _admin_view(admin.activate.execute(str(product_id)))

    @router.post("/{product_id}/deactivate")
    def deactivate(product_id: uuid.UUID) -> dict:
        return _admin_view(admin.deactivate.execute(str(product_id)))

    @router.delete("/{product_id}", status_code=204)
    def delete(product_id: uuid.UUID) -> Response:
        admin.delete.execute(str(product_id))
        return Response(status_code=204)

    return router
