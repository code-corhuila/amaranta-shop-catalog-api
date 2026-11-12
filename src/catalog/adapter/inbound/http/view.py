"""What a client sees of a product. The domain entity is never serialized: the adapter translates it, so renaming a field
inside the domain cannot break a client. The names are the monolith's, so the web does not notice the move."""

from collections.abc import Callable
from typing import TypeVar

from catalog.application.page import Page
from catalog.domain.model.product import Product

T = TypeVar("T")


def page_view(result: Page[T], item_view: Callable[[T], dict]) -> dict:
    """A page as every list of the API answers it: {data, meta} (the contract the web reads)."""
    return {"data": [item_view(item) for item in result.data],
            "meta": {"page": result.page, "limit": result.limit, "total": result.total, "totalPages": result.total_pages}}


def format_pesos(pesos: int) -> str:
    """Whole pesos as the web has always shown them: "$ 102.500", with a non-breaking space."""
    return "$ " + f"{pesos:,}".replace(",", ".")


def product_view(product: Product) -> dict:
    return {"id": product.id, "sku": product.sku, "name": product.name, "description": product.description,
            "category": product.category.value, "price": product.price, "priceFormatted": format_pesos(product.price),
            "stockQuantity": product.stock_quantity, "inStock": product.stock_quantity > 0, "imageUrl": product.image_url}
