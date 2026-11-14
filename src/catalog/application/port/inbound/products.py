"""What the catalog offers to people (Annex C): the public browses the products and the ADMIN role administers them.
The stock that Sales takes is in stock.py.

These are the only names the HTTP adapter knows. It never imports the classes that implement them, so a use case can be
replaced, and a test can hand the adapter any implementation of a port.
"""

from dataclasses import dataclass
from typing import Protocol

from catalog.application.page import Page
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


@dataclass(frozen=True)
class ProductChanges:
    """The fields of a product to change. A field left as UNSET is not touched; None is a value, so it is not "not given"."""

    name: object = UNSET
    description: object = UNSET
    category: object = UNSET
    price: object = UNSET
    image_url: object = UNSET


# ---- the public ----------------------------------------------------------------------------------------------------

class ListActiveProducts(Protocol):
    def execute(self, page: int, limit: int) -> Page[Product]:
        """The active products sorted by name, one bounded page at a time. Raises ValueError for a page or limit out of range."""


class GetProduct(Protocol):
    def execute(self, product_id: str) -> Product:
        """One product of the shop. Raises ProductNotFoundError if it does not exist or is inactive."""


# ---- the administrator ---------------------------------------------------------------------------------------------

class ListAllProducts(Protocol):
    def execute(self, page: int, limit: int) -> Page[Product]:
        """Every product, active or not, one bounded page at a time."""


class CreateProduct(Protocol):
    def execute(self, new: NewProduct) -> Product:
        """Raises BusinessRuleViolation: SKU_ALREADY_EXISTS, or the rule of the aggregate that the new product breaks."""


class UpdateProduct(Protocol):
    def execute(self, product_id: str, changes: ProductChanges) -> Product:
        """Changes only the fields given. Raises ProductNotFoundError."""


class SetProductStock(Protocol):
    def execute(self, product_id: str, quantity: int) -> Product:
        """Sets the stock exactly (zero or more). Raises ProductNotFoundError."""


class ActivateProduct(Protocol):
    def execute(self, product_id: str) -> Product:
        """Puts the product back on sale. Raises ProductNotFoundError."""


class DeactivateProduct(Protocol):
    def execute(self, product_id: str) -> Product:
        """Takes the product off sale without deleting it. Raises ProductNotFoundError."""


class DeleteProduct(Protocol):
    def execute(self, product_id: str) -> None:
        """Removes the product. Raises ProductNotFoundError."""


@dataclass(frozen=True)
class AdminProductPorts:
    """Everything the administration routes need, together: they are one surface, asked for in one place by the router."""

    list_all: ListAllProducts
    create: CreateProduct
    update: UpdateProduct
    set_stock: SetProductStock
    activate: ActivateProduct
    deactivate: DeactivateProduct
    delete: DeleteProduct
