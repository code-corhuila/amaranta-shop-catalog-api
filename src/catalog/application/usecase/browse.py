from catalog.application.errors import ProductNotFoundError
from catalog.application.page import Page, ensure_valid_request
from catalog.application.port.outbound.products import ProductRepository
from catalog.domain.model.product import Product


class ListActiveProductsService:
    """The active products, sorted by name, one bounded page at a time. A product out of stock is still listed."""

    def __init__(self, products: ProductRepository) -> None:
        self._products = products

    def execute(self, page: int, limit: int) -> Page[Product]:
        ensure_valid_request(page, limit)
        return self._products.find_active_page(page, limit)


class GetProductService:
    """One product of the shop. An inactive product does not exist for the public."""

    def __init__(self, products: ProductRepository) -> None:
        self._products = products

    def execute(self, product_id: str) -> Product:
        product = self._products.find_by_id(product_id)
        if product is None or not product.is_active:
            raise ProductNotFoundError(product_id)
        return product
