from typing import Protocol

from catalog.application.page import Page
from catalog.domain.model.product import Product


class ProductRepository(Protocol):
    def find_by_ids(self, ids: list[str]) -> list[Product]:
        """The products that exist among ids, in no particular order."""

    def find_by_id(self, product_id: str) -> Product | None:
        """One product, or None."""

    def find_active_page(self, page: int, limit: int) -> Page[Product]:
        """The active products sorted by name then id, one page (starting at 1) at a time, with the total."""

    def try_decrement_stock(self, product_id: str, quantity: int, now) -> bool:
        """Takes the units in ONE conditional write: the product is active AND has at least quantity.

        Never read-then-decrement-then-write: two requests for the last unit race the same write and the database lets only
        one win. Returns False when the write matched nothing, whether this request lacked the stock or lost the race.
        """

    def increment_stock(self, product_id: str, quantity: int, now) -> None:
        """Gives units back, atomically and unconditionally. A product that does not exist is skipped."""
