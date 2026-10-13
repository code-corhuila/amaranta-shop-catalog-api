"""What Catalog offers to Sales: take the stock of some products, or give it back (spec DP-8).

The routes are internal: the gateway never publishes them, so only the services of the platform can call them.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class StockItem:
    product_id: str
    quantity: int


@dataclass(frozen=True)
class ReservedLine:
    """A line taken from the stock, with the name and the price Sales will freeze in the order (RN-12)."""

    product_id: str
    product_name: str
    unit_price_amount: int
    quantity: int


class ReserveStock(Protocol):
    def execute(self, items: list[StockItem]) -> list[ReservedLine]:
        """Takes every line or none. Raises BusinessRuleViolation: PRODUCT_NOT_FOUND, INV-PRODUCT-002 or an input rule."""


class ReleaseStock(Protocol):
    def execute(self, items: list[StockItem]) -> None:
        """Gives back what a reservation took. A product that no longer exists is skipped, not an error."""
