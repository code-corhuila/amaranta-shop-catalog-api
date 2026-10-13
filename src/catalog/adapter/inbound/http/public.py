"""The public side of the catalog. Buying does not require an account (spec DP-1), so neither does browsing: these routes
ask for no token, and the gateway lets them through for the same reason."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from catalog.adapter.inbound.http.view import product_view
from catalog.application.page import MAX_LIMIT
from catalog.application.usecase.browse import GetProductService, ListActiveProductsService


def public_router(list_products: ListActiveProductsService, get_product: GetProductService) -> APIRouter:
    router = APIRouter(prefix="/api/v1/products")

    @router.get("")
    def list_(page: Annotated[int, Query(ge=1)] = 1, limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 20) -> dict:
        result = list_products.execute(page, limit)
        return {"data": [product_view(p) for p in result.data],
                "meta": {"page": result.page, "limit": result.limit, "total": result.total, "totalPages": result.total_pages}}

    @router.get("/{product_id}")
    def by_id(product_id: uuid.UUID) -> dict:
        return product_view(get_product.execute(str(product_id)))

    return router
