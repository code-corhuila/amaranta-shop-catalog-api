"""What an administrator does with the products, one class per operation. Every rule is the aggregate's; these classes only
find, save and stamp.

Deleting is safe: an order keeps its own copy of the name and the price (RN-12), and it refers to the product by id only,
with no foreign key, so a past order shows what it showed the day it was placed.
"""

from catalog.application.errors import ProductNotFoundError
from catalog.application.page import Page, ensure_valid_request
from catalog.application.port.inbound.products import AdminProductPorts, NewProduct, ProductChanges
from catalog.application.port.outbound.clock import Clock
from catalog.application.port.outbound.ids import IdGenerator
from catalog.application.port.outbound.products import ProductRepository
from catalog.domain.model.errors import BusinessRuleViolation
from catalog.domain.model.product import Product


def _load(products: ProductRepository, product_id: str) -> Product:
    product = products.find_by_id(product_id)
    if product is None:
        raise ProductNotFoundError(product_id)
    return product


class ListAllProductsService:
    def __init__(self, products: ProductRepository) -> None:
        self._products = products

    def execute(self, page: int, limit: int) -> Page[Product]:
        ensure_valid_request(page, limit)
        return self._products.find_all_page(page, limit)


class CreateProductService:
    def __init__(self, products: ProductRepository, clock: Clock, ids: IdGenerator) -> None:
        self._products = products
        self._clock = clock
        self._ids = ids

    def execute(self, new: NewProduct) -> Product:
        product = Product.create(product_id=self._ids.new_id(), sku=new.sku, name=new.name, description=new.description,
                                 category=new.category, price=new.price, stock_quantity=new.stock_quantity,
                                 image_url=new.image_url, now=self._clock.now())
        if self._products.find_by_sku(product.sku) is not None:
            raise BusinessRuleViolation("SKU_ALREADY_EXISTS", f'a product with sku "{product.sku}" already exists')
        self._products.save(product)
        return product


class UpdateProductService:
    def __init__(self, products: ProductRepository, clock: Clock) -> None:
        self._products = products
        self._clock = clock

    def execute(self, product_id: str, changes: ProductChanges) -> Product:
        product = _load(self._products, product_id)
        product.update_details(self._clock.now(), name=changes.name, description=changes.description,
                               category=changes.category, price=changes.price, image_url=changes.image_url)
        self._products.save(product)
        return product


class SetProductStockService:
    def __init__(self, products: ProductRepository, clock: Clock) -> None:
        self._products = products
        self._clock = clock

    def execute(self, product_id: str, quantity: int) -> Product:
        product = _load(self._products, product_id)
        product.set_stock(quantity, self._clock.now())
        self._products.save(product)
        return product


class ActivateProductService:
    def __init__(self, products: ProductRepository, clock: Clock) -> None:
        self._products = products
        self._clock = clock

    def execute(self, product_id: str) -> Product:
        product = _load(self._products, product_id)
        product.activate(self._clock.now())
        self._products.save(product)
        return product


class DeactivateProductService:
    def __init__(self, products: ProductRepository, clock: Clock) -> None:
        self._products = products
        self._clock = clock

    def execute(self, product_id: str) -> Product:
        product = _load(self._products, product_id)
        product.deactivate(self._clock.now())
        self._products.save(product)
        return product


class DeleteProductService:
    def __init__(self, products: ProductRepository) -> None:
        self._products = products

    def execute(self, product_id: str) -> None:
        _load(self._products, product_id)
        self._products.delete_by_id(product_id)


def build_admin_ports(products: ProductRepository, clock: Clock, ids: IdGenerator) -> AdminProductPorts:
    """The administration surface with its seven operations: the one place that says which classes make it up."""
    return AdminProductPorts(
        list_all=ListAllProductsService(products),
        create=CreateProductService(products, clock, ids),
        update=UpdateProductService(products, clock),
        set_stock=SetProductStockService(products, clock),
        activate=ActivateProductService(products, clock),
        deactivate=DeactivateProductService(products, clock),
        delete=DeleteProductService(products),
    )
