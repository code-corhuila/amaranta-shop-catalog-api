"""The Product aggregate and its rules (spec section 4; ADR-010). Each test names the rule it proves."""

from datetime import datetime, timedelta, timezone

import pytest

from catalog.domain.model.category import Category
from catalog.domain.model.errors import BusinessRuleViolation
from catalog.domain.model.product import Product

NOW = datetime(2026, 10, 12, 15, 0, tzinfo=timezone.utc)
LATER = NOW + timedelta(minutes=5)
ID = "399d2ea8-1ccb-4193-8255-1b51e331984d"


def make(**overrides) -> Product:
    fields = dict(product_id=ID, sku="FOOD-001", name="Dog food 3 kg", description="Dry food for adult dogs.",
                  category=Category.FOOD, price=45_000, stock_quantity=24, image_url="https://example.test/a.png", now=NOW)
    fields.update(overrides)
    return Product.create(**fields)


def rule_of(action) -> str:
    with pytest.raises(BusinessRuleViolation) as raised:
        action()
    return raised.value.rule_id


# creation -----------------------------------------------------------------------------------------------------------

def test_a_new_product_is_active_and_stamped_with_the_time_it_was_created():
    product = make()

    assert product.is_active is True
    assert product.created_at == NOW and product.updated_at == NOW
    assert product.id == ID


def test_the_text_fields_are_kept_without_their_surrounding_spaces():
    product = make(sku="  FOOD-001 ", name=" Dog food ", description="  Dry food. ")

    assert (product.sku, product.name, product.description) == ("FOOD-001", "Dog food", "Dry food.")


@pytest.mark.parametrize("sku", ["", " ", "A", "x" * 51])
def test_a_sku_is_between_2_and_50_characters(sku):
    assert rule_of(lambda: make(sku=sku)) == "INV-PRODUCT-004"


@pytest.mark.parametrize("name", ["", "   ", "x" * 121])
def test_a_name_is_between_1_and_120_characters(name):
    assert rule_of(lambda: make(name=name)) == "INV-PRODUCT-005"


@pytest.mark.parametrize("stock", [-1, 1.5, "3", True, None])
def test_the_stock_is_a_non_negative_whole_number(stock):
    assert rule_of(lambda: make(stock_quantity=stock)) == "INV-PRODUCT-006"


@pytest.mark.parametrize("price", [0, -1, 10.5, "100", True, None])
def test_the_price_is_a_positive_whole_number_of_pesos(price):
    assert rule_of(lambda: make(price=price)) == "INV-PRODUCT-007"


def test_the_description_and_the_image_url_have_the_limits_of_the_database():
    assert rule_of(lambda: make(description="x" * 501)) == "INV-PRODUCT-008"
    assert rule_of(lambda: make(image_url="x" * 501)) == "INV-PRODUCT-009"


def test_a_stock_of_zero_is_allowed():
    assert make(stock_quantity=0).stock_quantity == 0


def test_the_category_must_be_one_of_the_five():
    assert {c.value for c in Category} == {"FOOD", "ACCESSORIES", "HYGIENE", "MEDICATION", "TOYS"}
    assert rule_of(lambda: make(category="PETS")) == "INV-PRODUCT-010"


# stock (INV-PRODUCT-002: never below zero) ----------------------------------------------------------------------------

def test_decrementing_takes_the_units_and_stamps_the_change():
    product = make(stock_quantity=10)

    product.decrement_stock(4, LATER)

    assert product.stock_quantity == 6 and product.updated_at == LATER


def test_the_last_unit_can_be_taken_but_not_one_more():
    product = make(stock_quantity=2)

    product.decrement_stock(2, NOW)

    assert product.stock_quantity == 0
    assert rule_of(lambda: product.decrement_stock(1, NOW)) == "INV-PRODUCT-002"
    assert product.stock_quantity == 0


def test_decrementing_more_than_there_is_changes_nothing():
    product = make(stock_quantity=3)

    assert rule_of(lambda: product.decrement_stock(4, LATER)) == "INV-PRODUCT-002"
    assert product.stock_quantity == 3 and product.updated_at == NOW


@pytest.mark.parametrize("quantity", [0, -1, 1.5])
def test_only_a_positive_whole_quantity_can_be_decremented_or_restored(quantity):
    product = make()

    assert rule_of(lambda: product.decrement_stock(quantity, NOW)) == "INV-PRODUCT-003"
    assert rule_of(lambda: product.restore_stock(quantity, NOW)) == "INV-PRODUCT-003"


def test_restoring_gives_the_units_back():
    product = make(stock_quantity=5)

    product.restore_stock(3, LATER)

    assert product.stock_quantity == 8 and product.updated_at == LATER


# administration -------------------------------------------------------------------------------------------------------

def test_updating_the_details_changes_only_what_is_given():
    product = make()

    product.update_details(now=LATER, name=" New name ", price=50_000)

    assert (product.name, product.price) == ("New name", 50_000)
    assert (product.sku, product.category, product.description) == ("FOOD-001", Category.FOOD, "Dry food for adult dogs.")
    assert product.updated_at == LATER


def test_an_invalid_update_changes_nothing():
    product = make()

    assert rule_of(lambda: product.update_details(now=LATER, name="", price=50_000)) == "INV-PRODUCT-005"
    assert (product.name, product.price, product.updated_at) == ("Dog food 3 kg", 45_000, NOW)


def test_the_stock_can_be_set_to_zero_but_never_below():
    product = make()

    product.set_stock(0, LATER)

    assert product.stock_quantity == 0
    assert rule_of(lambda: product.set_stock(-1, LATER)) == "INV-PRODUCT-006"


def test_activating_and_deactivating_are_repeatable():
    product = make()

    product.deactivate(LATER)
    product.deactivate(LATER)
    assert product.is_active is False

    product.activate(LATER)
    assert product.is_active is True


def test_reconstituting_rebuilds_a_stored_product_without_judging_it():
    stored = make(stock_quantity=0)

    rebuilt = Product.reconstitute(id=stored.id, sku=stored.sku, name=stored.name, description=stored.description,
                                   category=stored.category, price=stored.price, stock_quantity=0,
                                   image_url=stored.image_url, is_active=False, created_at=NOW, updated_at=LATER)

    assert rebuilt.is_active is False and rebuilt.updated_at == LATER
