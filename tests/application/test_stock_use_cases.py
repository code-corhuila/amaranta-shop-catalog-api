"""Reserving and releasing stock for Sales (spec DP-8, rules RN-08 and RN-09; ADR-010).

The repository is a double with the same atomic contract as MongoDB's: one conditional write that either takes the
units or does not. The race itself is proved against a real MongoDB in tests/integration.
"""

import pytest

from catalog.application.port.inbound.stock import StockItem
from catalog.application.usecase.release_stock import ReleaseStockService
from catalog.application.usecase.reserve_stock import ReserveStockService
from catalog.domain.model.errors import BusinessRuleViolation
from tests.application.fakes import CAT_TOY, DOG_FOOD, UNKNOWN, FakeClock, FakeProducts, product


@pytest.fixture
def products() -> FakeProducts:
    return FakeProducts(product(DOG_FOOD, "Dog food 3 kg", 45_000, stock=10), product(CAT_TOY, "Cat toy", 12_500, stock=3))


@pytest.fixture
def reserve(products) -> ReserveStockService:
    return ReserveStockService(products, FakeClock())


def rule_of(action) -> str:
    with pytest.raises(BusinessRuleViolation) as raised:
        action()
    return raised.value.rule_id


# reserve ------------------------------------------------------------------------------------------------------------

def test_reserving_takes_the_units_and_answers_with_the_name_and_the_price_of_each_line(reserve, products):
    lines = reserve.execute([StockItem(DOG_FOOD, 4), StockItem(CAT_TOY, 1)])

    assert [(l.product_id, l.product_name, l.unit_price_amount, l.quantity) for l in lines] == [
        (DOG_FOOD, "Dog food 3 kg", 45_000, 4), (CAT_TOY, "Cat toy", 12_500, 1)]
    assert (products.stock_of(DOG_FOOD), products.stock_of(CAT_TOY)) == (6, 2)


def test_the_last_unit_can_be_reserved(reserve, products):
    reserve.execute([StockItem(CAT_TOY, 3)])

    assert products.stock_of(CAT_TOY) == 0


def test_an_unknown_product_is_rejected_and_nothing_is_taken(reserve, products):
    assert rule_of(lambda: reserve.execute([StockItem(DOG_FOOD, 1), StockItem(UNKNOWN, 1)])) == "PRODUCT_NOT_FOUND"

    assert products.stock_of(DOG_FOOD) == 10 and products.decrements == 0


def test_an_inactive_product_cannot_be_reserved(reserve, products):
    products.by_id[DOG_FOOD].is_active = False

    assert rule_of(lambda: reserve.execute([StockItem(DOG_FOOD, 1)])) == "PRODUCT_NOT_FOUND"
    assert products.decrements == 0


def test_not_enough_stock_is_rejected_before_anything_is_written(reserve, products):
    assert rule_of(lambda: reserve.execute([StockItem(DOG_FOOD, 1), StockItem(CAT_TOY, 4)])) == "INV-PRODUCT-002"

    assert (products.stock_of(DOG_FOOD), products.stock_of(CAT_TOY)) == (10, 3) and products.decrements == 0


def test_losing_the_race_for_a_later_line_gives_the_earlier_lines_back(reserve, products):
    products.lost_the_race_for = {CAT_TOY}   # the check passed, but another request took the unit before the write

    assert rule_of(lambda: reserve.execute([StockItem(DOG_FOOD, 4), StockItem(CAT_TOY, 1)])) == "INV-PRODUCT-002"

    assert (products.stock_of(DOG_FOOD), products.stock_of(CAT_TOY)) == (10, 3)   # all or nothing


def test_an_empty_request_and_a_repeated_product_are_refused(reserve, products):
    assert rule_of(lambda: reserve.execute([])) == "INV-STOCK-001"
    assert rule_of(lambda: reserve.execute([StockItem(DOG_FOOD, 1), StockItem(DOG_FOOD, 2)])) == "INV-STOCK-002"
    assert products.decrements == 0


@pytest.mark.parametrize("quantity", [0, -1])
def test_a_quantity_that_is_not_positive_is_refused(reserve, quantity):
    assert rule_of(lambda: reserve.execute([StockItem(DOG_FOOD, quantity)])) == "INV-PRODUCT-003"


# release ------------------------------------------------------------------------------------------------------------

def test_releasing_gives_the_units_back(products):
    ReserveStockService(products, FakeClock()).execute([StockItem(DOG_FOOD, 4)])

    ReleaseStockService(products, FakeClock()).execute([StockItem(DOG_FOOD, 4)])

    assert products.stock_of(DOG_FOOD) == 10


def test_releasing_a_product_that_no_longer_exists_is_not_an_error(products):
    ReleaseStockService(products, FakeClock()).execute([StockItem(UNKNOWN, 2), StockItem(CAT_TOY, 1)])

    assert products.stock_of(CAT_TOY) == 4


def test_releasing_refuses_a_quantity_that_is_not_positive(products):
    assert rule_of(lambda: ReleaseStockService(products, FakeClock()).execute([StockItem(CAT_TOY, 0)])) == "INV-PRODUCT-003"
