from dataclasses import dataclass
from datetime import datetime

from catalog.domain.model.category import Category
from catalog.domain.model.errors import BusinessRuleViolation

UNSET = object()  # "not given", as opposed to None: update_details changes only what is given


def _is_whole(value: object) -> bool:
    """A whole number, and not a bool (which Python counts as an int) nor a float."""
    return isinstance(value, int) and not isinstance(value, bool)


def _check_sku(sku: str) -> str:
    sku = sku.strip()
    if not 2 <= len(sku) <= 50:
        raise BusinessRuleViolation("INV-PRODUCT-004", "sku must be between 2 and 50 characters")
    return sku


def _check_name(name: str) -> str:
    name = name.strip()
    if not 1 <= len(name) <= 120:
        raise BusinessRuleViolation("INV-PRODUCT-005", "name must be between 1 and 120 characters")
    return name


def _check_stock(stock: object) -> int:
    if not _is_whole(stock) or stock < 0:
        raise BusinessRuleViolation("INV-PRODUCT-006", "stockQuantity must be a non-negative whole number")
    return stock


def _check_price(price: object) -> int:
    if not _is_whole(price) or price < 1:
        raise BusinessRuleViolation("INV-PRODUCT-007", "price must be a positive whole number of pesos")
    return price


def _check_description(description: str) -> str:
    description = description.strip()
    if len(description) > 500:
        raise BusinessRuleViolation("INV-PRODUCT-008", "description must have at most 500 characters")
    return description


def _check_image_url(image_url: str) -> str:
    if len(image_url) > 500:
        raise BusinessRuleViolation("INV-PRODUCT-009", "imageUrl must have at most 500 characters")
    return image_url


def _check_category(category: object) -> Category:
    try:
        return Category(category)
    except ValueError:
        raise BusinessRuleViolation("INV-PRODUCT-010", "category must be one of " + ", ".join(c.value for c in Category)) from None


def _check_quantity(quantity: object) -> int:
    if not _is_whole(quantity) or quantity <= 0:
        raise BusinessRuleViolation("INV-PRODUCT-003", "the quantity must be a positive whole number")
    return quantity


@dataclass
class Product:
    """The Product aggregate root of the catalog domain.

    Money and stock are whole numbers (pesos and units). The stock never goes below zero (INV-PRODUCT-002), and the
    aggregate refuses to exist in an invalid state whoever calls it. Time comes in as an argument: the domain reads no clock.
    """

    id: str
    sku: str
    name: str
    description: str
    category: Category
    price: int
    stock_quantity: int
    image_url: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def create(cls, product_id: str, sku: str, name: str, description: str, category: object, price: object,
               stock_quantity: object, image_url: str, now: datetime) -> "Product":
        return cls(id=product_id, sku=_check_sku(sku), name=_check_name(name),
                   description=_check_description(description), category=_check_category(category),
                   price=_check_price(price), stock_quantity=_check_stock(stock_quantity),
                   image_url=_check_image_url(image_url), is_active=True, created_at=now, updated_at=now)

    @classmethod
    def reconstitute(cls, **fields) -> "Product":
        """Rebuilds a stored product exactly as it was read. It judges nothing: it is history."""
        return cls(**fields)

    def has_stock_for(self, quantity: int) -> bool:
        return self.stock_quantity >= quantity

    def decrement_stock(self, quantity: int, now: datetime) -> None:
        """INV-PRODUCT-002: the stock never goes below zero."""
        _check_quantity(quantity)
        if not self.has_stock_for(quantity):
            raise BusinessRuleViolation(
                "INV-PRODUCT-002", f'"{self.name}" only has {self.stock_quantity} unit(s) left (requested {quantity})')
        self.stock_quantity -= quantity
        self.updated_at = now

    def restore_stock(self, quantity: int, now: datetime) -> None:
        _check_quantity(quantity)
        self.stock_quantity += quantity
        self.updated_at = now

    def update_details(self, now: datetime, name=UNSET, description=UNSET, category=UNSET, price=UNSET,
                       image_url=UNSET) -> None:
        """Changes only what is given. Everything is judged before anything changes, so a failure leaves the product as it was."""
        changes = {}
        if name is not UNSET:
            changes["name"] = _check_name(name)
        if description is not UNSET:
            changes["description"] = _check_description(description)
        if category is not UNSET:
            changes["category"] = _check_category(category)
        if price is not UNSET:
            changes["price"] = _check_price(price)
        if image_url is not UNSET:
            changes["image_url"] = _check_image_url(image_url)
        for field, value in changes.items():
            setattr(self, field, value)
        self.updated_at = now

    def set_stock(self, quantity: int, now: datetime) -> None:
        self.stock_quantity = _check_stock(quantity)
        self.updated_at = now

    def activate(self, now: datetime) -> None:
        self.is_active = True
        self.updated_at = now

    def deactivate(self, now: datetime) -> None:
        self.is_active = False
        self.updated_at = now
