"""Doubles of the output ports. They record what the use case did, so a test can say what must NOT have happened."""

from datetime import datetime, timezone

from catalog.application.page import Page
from catalog.domain.model.category import Category
from catalog.domain.model.product import Product

NOW = datetime(2026, 10, 12, 15, 0, tzinfo=timezone.utc)
DOG_FOOD = "399d2ea8-1ccb-4193-8255-1b51e331984d"
CAT_TOY = "13aaba9d-5a94-4384-9558-50f158701a2e"
UNKNOWN = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"


def product(product_id=DOG_FOOD, name="Dog food 3 kg", price=45_000, stock=10, sku=None) -> Product:
    return Product.create(product_id=product_id, sku=sku or "SKU-" + product_id[:4], name=name, description="", category=Category.FOOD,
                          price=price, stock_quantity=stock, image_url="https://example.test/a.png", now=NOW)


class FakeClock:
    def now(self) -> datetime:
        return NOW


class SequentialIds:
    def __init__(self) -> None:
        self._next = 1

    def new_id(self) -> str:
        self._next += 1
        return f"00000000-0000-4000-8000-{self._next:012d}"


class FakeProducts:
    """A product repository in a dict, with the same atomic contract as the real one."""

    def __init__(self, *products: Product) -> None:
        self.by_id = {p.id: p for p in products}
        self.lost_the_race_for: set[str] = set()   # products another request "took" between the check and the write
        self.decrements = 0

    def find_by_ids(self, ids):
        return [self.by_id[i] for i in ids if i in self.by_id]

    def find_by_id(self, product_id):
        return self.by_id.get(product_id)

    def find_active_page(self, page, limit) -> Page:
        active = sorted((p for p in self.by_id.values() if p.is_active), key=lambda p: (p.name, p.id))
        return Page(active[(page - 1) * limit: page * limit], page, limit, len(active))

    def find_by_sku(self, sku):
        return next((p for p in self.by_id.values() if p.sku == sku), None)

    def find_all_page(self, page, limit) -> Page:
        everything = sorted(self.by_id.values(), key=lambda p: (p.name, p.id))
        return Page(everything[(page - 1) * limit: page * limit], page, limit, len(everything))

    def save(self, product) -> None:
        self.by_id[product.id] = product

    def delete_by_id(self, product_id) -> None:
        self.by_id.pop(product_id, None)

    def try_decrement_stock(self, product_id, quantity, now) -> bool:
        self.decrements += 1
        p = self.by_id.get(product_id)
        if p is None or product_id in self.lost_the_race_for or not p.is_active or p.stock_quantity < quantity:
            return False
        p.stock_quantity -= quantity
        return True

    def increment_stock(self, product_id, quantity, now) -> None:
        if product_id in self.by_id:
            self.by_id[product_id].stock_quantity += quantity

    def stock_of(self, product_id) -> int:
        return self.by_id[product_id].stock_quantity
