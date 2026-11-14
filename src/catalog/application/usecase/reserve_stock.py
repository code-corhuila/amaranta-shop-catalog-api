from catalog.application.port.inbound.stock import ReservedLine, ReserveStock, StockItem
from catalog.application.port.outbound.clock import Clock
from catalog.application.port.outbound.products import ProductRepository
from catalog.domain.model.errors import BusinessRuleViolation


def validate_items(items: list[StockItem], *, allow_empty: bool = False) -> None:
    if not items and not allow_empty:
        raise BusinessRuleViolation("INV-STOCK-001", "at least one item is required")
    for item in items:
        if not isinstance(item.quantity, int) or isinstance(item.quantity, bool) or item.quantity <= 0:
            raise BusinessRuleViolation("INV-PRODUCT-003", "the quantity must be a positive whole number")
    ids = [item.product_id for item in items]
    if len(set(ids)) != len(ids):
        raise BusinessRuleViolation("INV-STOCK-002", "a product can appear only once in a request")


class ReserveStockService(ReserveStock):
    """Takes the stock of every line or of none (spec DP-8, RN-08).

    A first pass fails fast on what is obviously impossible, but it is only a snapshot that may be stale a moment later.
    The authority is the conditional write of each line: if a later line cannot be taken, because it lacks the stock or
    because another request won the race for the last unit, the lines already taken are given back before the error goes
    out. So a rejected reservation leaves the stock exactly as it was.
    """

    def __init__(self, products: ProductRepository, clock: Clock) -> None:
        self._products = products
        self._clock = clock

    def execute(self, items: list[StockItem]) -> list[ReservedLine]:
        validate_items(items)
        by_id = {p.id: p for p in self._products.find_by_ids([i.product_id for i in items])}

        for item in items:
            product = by_id.get(item.product_id)
            if product is None or not product.is_active:
                raise BusinessRuleViolation("PRODUCT_NOT_FOUND", f"product {item.product_id} does not exist or is inactive")
            if not product.has_stock_for(item.quantity):
                raise self._not_enough(product.name, product.stock_quantity, item.quantity)

        now = self._clock.now()
        taken: list[StockItem] = []
        try:
            for item in items:
                if not self._products.try_decrement_stock(item.product_id, item.quantity, now):
                    current = self._products.find_by_ids([item.product_id])
                    raise self._not_enough(by_id[item.product_id].name, current[0].stock_quantity if current else 0, item.quantity)
                taken.append(item)
        except Exception:
            for item in taken:
                self._products.increment_stock(item.product_id, item.quantity, now)
            raise

        return [ReservedLine(i.product_id, by_id[i.product_id].name, by_id[i.product_id].price, i.quantity) for i in items]

    @staticmethod
    def _not_enough(name: str, available: int, requested: int) -> BusinessRuleViolation:
        return BusinessRuleViolation("INV-PRODUCT-002", f'"{name}" only has {available} unit(s) left (requested {requested})')
