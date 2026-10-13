"""What a client sees of a product. The domain entity is never serialized: the adapter translates it, so renaming a field
inside the domain cannot break a client. The names are the monolith's, so the web does not notice the move."""

from catalog.domain.model.product import Product


def format_pesos(pesos: int) -> str:
    """Whole pesos as the web has always shown them: "$ 102.500", with a non-breaking space."""
    return "$ " + f"{pesos:,}".replace(",", ".")


def product_view(product: Product) -> dict:
    return {"id": product.id, "sku": product.sku, "name": product.name, "description": product.description,
            "category": product.category.value, "price": product.price, "priceFormatted": format_pesos(product.price),
            "stockQuantity": product.stock_quantity, "inStock": product.stock_quantity > 0, "imageUrl": product.image_url}
