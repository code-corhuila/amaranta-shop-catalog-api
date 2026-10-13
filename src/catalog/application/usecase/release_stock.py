from catalog.application.port.inbound.stock import ReleaseStock, StockItem
from catalog.application.port.outbound.clock import Clock
from catalog.application.port.outbound.products import ProductRepository
from catalog.application.usecase.reserve_stock import validate_items


class ReleaseStockService(ReleaseStock):
    """Gives back what a reservation took. Sales calls it at most once per reservation and never retries it, because a retry
    would credit the stock twice; for the same reason a product that has been deleted since is skipped, not an error."""

    def __init__(self, products: ProductRepository, clock: Clock) -> None:
        self._products = products
        self._clock = clock

    def execute(self, items: list[StockItem]) -> None:
        validate_items(items, allow_empty=True)
        now = self._clock.now()
        for item in items:
            self._products.increment_stock(item.product_id, item.quantity, now)
