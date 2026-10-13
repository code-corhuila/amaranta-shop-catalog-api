"""Administering the products (monolith: AdminCatalogController). An administrator creates, edits, sets the stock of,
activates, deactivates and deletes. Deleting is safe because an order keeps its own copy of the name and the price (RN-12)."""

import pytest

from catalog.application.errors import ProductNotFoundError
from catalog.application.usecase.admin import AdminProducts, NewProduct
from catalog.domain.model.category import Category
from catalog.domain.model.errors import BusinessRuleViolation
from tests.application.fakes import DOG_FOOD, NOW, UNKNOWN, FakeClock, FakeProducts, SequentialIds, product


@pytest.fixture
def products() -> FakeProducts:
    return FakeProducts(product(DOG_FOOD, "Dog food 3 kg", 45_000, stock=10, sku="FOOD-001"))


@pytest.fixture
def admin(products) -> AdminProducts:
    return AdminProducts(products, FakeClock(), SequentialIds())


def new(**overrides) -> NewProduct:
    fields = dict(sku="TOY-009", name="Rope toy", description="A rope.", category="TOYS", price=9_000, stock_quantity=4,
                  image_url="https://example.test/rope.png")
    fields.update(overrides)
    return NewProduct(**fields)


def rule_of(action) -> str:
    with pytest.raises(BusinessRuleViolation) as raised:
        action()
    return raised.value.rule_id


def test_creating_stores_an_active_product_with_a_new_id_stamped_by_the_clock(admin, products):
    created = admin.create(new())

    assert created.is_active and created.category is Category.TOYS and created.created_at == NOW
    assert products.find_by_id(created.id) is created


def test_a_sku_that_already_exists_is_refused(admin, products):
    assert rule_of(lambda: admin.create(new(sku="FOOD-001"))) == "SKU_ALREADY_EXISTS"
    assert len(products.by_id) == 1


def test_an_invalid_product_is_refused_with_the_rule_that_it_breaks(admin, products):
    assert rule_of(lambda: admin.create(new(price=0))) == "INV-PRODUCT-007"
    assert rule_of(lambda: admin.create(new(name=""))) == "INV-PRODUCT-005"
    assert rule_of(lambda: admin.create(new(category="PETS"))) == "INV-PRODUCT-010"
    assert len(products.by_id) == 1


def test_updating_changes_only_the_fields_given(admin):
    updated = admin.update(DOG_FOOD, price=50_000, name="Dog food 5 kg")

    assert (updated.price, updated.name, updated.sku, updated.stock_quantity) == (50_000, "Dog food 5 kg", "FOOD-001", 10)


def test_the_stock_can_be_set_to_zero_but_not_below(admin, products):
    assert admin.set_stock(DOG_FOOD, 0).stock_quantity == 0
    assert rule_of(lambda: admin.set_stock(DOG_FOOD, -1)) == "INV-PRODUCT-006"
    assert products.stock_of(DOG_FOOD) == 0


def test_a_product_is_deactivated_and_activated_again(admin):
    assert admin.set_active(DOG_FOOD, False).is_active is False
    assert admin.set_active(DOG_FOOD, True).is_active is True


def test_deleting_removes_the_product(admin, products):
    admin.delete(DOG_FOOD)

    assert products.find_by_id(DOG_FOOD) is None


@pytest.mark.parametrize("action", [
    lambda a: a.update(UNKNOWN, price=1_000),
    lambda a: a.set_stock(UNKNOWN, 1),
    lambda a: a.set_active(UNKNOWN, True),
    lambda a: a.delete(UNKNOWN),
])
def test_acting_on_a_product_that_does_not_exist_is_not_found(admin, action):
    with pytest.raises(ProductNotFoundError):
        action(admin)


def test_the_administrator_sees_every_product_including_the_inactive_ones(admin, products):
    admin.set_active(DOG_FOOD, False)
    admin.create(new())

    page = admin.list_all(page=1, limit=20)

    assert {p.sku for p in page.data} == {"FOOD-001", "TOY-009"} and page.total == 2


@pytest.mark.parametrize("page,limit", [(0, 20), (1, 0), (1, 101)])
def test_the_list_is_bounded(admin, page, limit):
    with pytest.raises(ValueError):
        admin.list_all(page=page, limit=limit)
