from dataclasses import dataclass

from catalog.application.errors import ProductNotFoundError
from catalog.application.page import MAX_LIMIT, Page
from catalog.application.port.outbound.clock import Clock
from catalog.application.port.outbound.ids import IdGenerator
from catalog.application.port.outbound.products import ProductRepository
from catalog.domain.model.errors import BusinessRuleViolation
from catalog.domain.model.product import UNSET, Product


@dataclass(frozen=True)
class NewProduct:
    sku: str
    name: str
    description: str
    category: str
    price: int
    stock_quantity: int
    image_url: str


class AdminProducts:
    """What an administrator does with the products. Every rule is the aggregate's; this class only finds, saves and stamps.

    Deleting is safe: an order keeps its own copy of the name and the price (RN-12), and it refers to the product by id
    only, with no foreign key, so a past order shows what it showed the day it was placed.
    """

    def __init__(self, products: ProductRepository, clock: Clock, ids: IdGenerator) -> None:
        self._products = products
        self._clock = clock
        self._ids = ids

    def list_all(self, page: int, limit: int) -> Page[Product]:
        if page < 1:
            raise ValueError("page must be 1 or more")
        if not 1 <= limit <= MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")
        return self._products.find_all_page(page, limit)

    def create(self, new: NewProduct) -> Product:
        product = Product.create(product_id=self._ids.new_id(), sku=new.sku, name=new.name, description=new.description,
                                 category=new.category, price=new.price, stock_quantity=new.stock_quantity,
                                 image_url=new.image_url, now=self._clock.now())
        if self._products.find_by_sku(product.sku) is not None:
            raise BusinessRuleViolation("SKU_ALREADY_EXISTS", f'a product with sku "{product.sku}" already exists')
        self._products.save(product)
        return product

    def update(self, product_id: str, name=UNSET, description=UNSET, category=UNSET, price=UNSET, image_url=UNSET) -> Product:
        product = self._load(product_id)
        product.update_details(self._clock.now(), name=name, description=description, category=category, price=price, image_url=image_url)
        self._products.save(product)
        return product

    def set_stock(self, product_id: str, quantity: int) -> Product:
        product = self._load(product_id)
        product.set_stock(quantity, self._clock.now())
        self._products.save(product)
        return product

    def set_active(self, product_id: str, active: bool) -> Product:
        product = self._load(product_id)
        (product.activate if active else product.deactivate)(self._clock.now())
        self._products.save(product)
        return product

    def delete(self, product_id: str) -> None:
        self._load(product_id)
        self._products.delete_by_id(product_id)

    def _load(self, product_id: str) -> Product:
        product = self._products.find_by_id(product_id)
        if product is None:
            raise ProductNotFoundError(product_id)
        return product
