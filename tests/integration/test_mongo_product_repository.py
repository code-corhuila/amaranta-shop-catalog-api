"""The product repository against a real MongoDB with the database of catalog-db, connecting as catalog_app.

A double proves that the use case calls the repository; only the real engine proves that the conditional write is
atomic, that the types stay long and that the migration exists. Run it with `bash scripts/integration-test.sh`;
without TEST_MONGODB_URI it is skipped, not failed (Annex C).
"""

import os
import threading
import uuid
from datetime import datetime, timezone

import pytest
from bson import Int64
from pymongo import MongoClient

from catalog.adapter.outbound.persistence.mongo import MongoProductRepository
from catalog.application.port.inbound.stock import StockItem
from catalog.application.usecase.reserve_stock import ReserveStockService
from catalog.domain.model.category import Category
from catalog.domain.model.errors import BusinessRuleViolation
from catalog.domain.model.product import Product

URI = os.environ.get("TEST_MONGODB_URI")
ADMIN_URI = os.environ.get("TEST_MONGODB_ADMIN_URI")
pytestmark = pytest.mark.skipif(not URI, reason="TEST_MONGODB_URI is not set: run scripts/integration-test.sh")

NOW = datetime(2026, 10, 12, 15, 0, tzinfo=timezone.utc)


class Clock:
    def now(self) -> datetime:
        return NOW


@pytest.fixture
def repository():
    return MongoProductRepository(MongoClient(URI, tz_aware=True).get_default_database())


@pytest.fixture
def admin():
    """The administrator inserts and removes the test products: catalog_app, by design, cannot create what it should not."""
    collection = MongoClient(ADMIN_URI, tz_aware=True).get_default_database().product
    created = []

    def add(stock: int, active: bool = True, name: str = "Test product") -> str:
        product_id = str(uuid.uuid4())
        collection.insert_one({"_id": product_id, "sku": "IT-" + product_id[:8], "name": name, "description": "",
                               "category": "TOYS", "price": Int64(1_000), "stockQuantity": Int64(stock), "imageUrl": "https://example.test/p.png",
                               "isActive": active, "createdAt": NOW, "updatedAt": NOW})
        created.append(product_id)
        return product_id

    add.raw = lambda product_id: collection.find_one({"_id": product_id})
    add.track = created.append   # a product the service itself created: the administrator removes it afterwards
    yield add
    collection.delete_many({"_id": {"$in": created}})


def test_it_finds_the_products_that_exist_among_the_ids_asked(repository, admin):
    first, second = admin(5), admin(7)

    found = repository.find_by_ids([first, second, str(uuid.uuid4())])

    assert {p.id: p.stock_quantity for p in found} == {first: 5, second: 7}


def test_the_seed_of_catalog_db_is_readable_by_the_service(repository):
    found = repository.find_by_ids(["399d2ea8-1ccb-4193-8255-1b51e331984d"])   # FOOD-001, the id the monolith issued

    assert [(p.sku, p.price) for p in found] == [("FOOD-001", 189_000)]


def test_one_product_is_read_back_whole(repository, admin):
    product_id = admin(7, name="Whole product")

    product = repository.find_by_id(product_id)

    assert (product.name, product.price, product.stock_quantity, product.is_active) == ("Whole product", 1_000, 7, True)
    assert product.created_at == NOW and repository.find_by_id(str(uuid.uuid4())) is None


def test_the_active_products_come_sorted_by_name_in_bounded_pages(repository, admin):
    admin(1, name="~zz last"), admin(1, name="~zz middle"), admin(1, name="~aa first"), admin(1, active=False, name="~hidden")

    everything = repository.find_active_page(1, 100)
    mine = [p.name for p in everything.data if p.name.startswith("~")]
    one = repository.find_active_page(1, 1)

    assert mine == ["~aa first", "~zz last", "~zz middle"]                # sorted, the inactive one left out
    assert [p.name for p in everything.data] == sorted(p.name for p in everything.data)
    assert len(one.data) == 1 and one.total == everything.total and one.total_pages == everything.total
    assert everything.total >= 13                                          # the ten seeded products and my three


def test_a_product_saved_by_the_service_reads_back_whole_with_long_money(repository, admin):
    product = Product.create(product_id=str(uuid.uuid4()), sku="IT-SAVE-" + uuid.uuid4().hex[:6], name="Saved", description="d",
                             category=Category.TOYS, price=2_500, stock_quantity=6, image_url="https://example.test/s.png", now=NOW)
    admin.track(product.id)

    repository.save(product)
    product.update_details(NOW, price=3_000)
    repository.save(product)   # the second save replaces, it does not duplicate

    raw = admin.raw(product.id)
    assert raw["price"] == 3_000 and isinstance(raw["price"], Int64) and isinstance(raw["stockQuantity"], Int64)
    assert repository.find_by_sku(product.sku).id == product.id and repository.find_by_sku("nope-nope") is None


def test_the_unique_sku_is_enforced_by_the_database_not_only_by_the_use_case(repository, admin):
    first = Product.create(product_id=str(uuid.uuid4()), sku="IT-DUP-" + uuid.uuid4().hex[:6], name="One", description="",
                           category=Category.FOOD, price=1_000, stock_quantity=1, image_url="https://example.test/1.png", now=NOW)
    second = Product.create(product_id=str(uuid.uuid4()), sku=first.sku, name="Two", description="", category=Category.FOOD,
                            price=1_000, stock_quantity=1, image_url="https://example.test/2.png", now=NOW)
    admin.track(first.id)
    repository.save(first)

    with pytest.raises(BusinessRuleViolation) as raised:
        repository.save(second)

    assert raised.value.rule_id == "SKU_ALREADY_EXISTS" and admin.raw(second.id) is None


def test_deleting_removes_the_product_and_deleting_it_again_is_harmless(repository, admin):
    product_id = admin(1)

    repository.delete_by_id(product_id)
    repository.delete_by_id(product_id)

    assert admin.raw(product_id) is None


def test_the_administrators_list_includes_the_inactive_products(repository, admin):
    hidden = admin(1, active=False, name="~hidden-for-admin")

    names = [p.name for p in repository.find_all_page(1, 100).data]

    assert "~hidden-for-admin" in names and hidden not in [p.id for p in repository.find_active_page(1, 100).data]


def test_taking_units_decrements_in_one_write_and_keeps_the_type_long(repository, admin):
    product_id = admin(10)

    assert repository.try_decrement_stock(product_id, 4, NOW) is True

    raw = admin.raw(product_id)
    assert raw["stockQuantity"] == 6 and isinstance(raw["stockQuantity"], Int64)   # the validator refuses an int32 or a double
    assert raw["updatedAt"] == NOW


def test_it_refuses_to_take_more_than_there_is_and_changes_nothing(repository, admin):
    product_id = admin(3)

    assert repository.try_decrement_stock(product_id, 4, NOW) is False
    assert admin.raw(product_id)["stockQuantity"] == 3
    assert repository.try_decrement_stock(product_id, 3, NOW) is True   # the last unit can be taken
    assert admin.raw(product_id)["stockQuantity"] == 0


def test_an_inactive_or_unknown_product_cannot_be_taken(repository, admin):
    inactive = admin(5, active=False)

    assert repository.try_decrement_stock(inactive, 1, NOW) is False
    assert repository.try_decrement_stock(str(uuid.uuid4()), 1, NOW) is False
    assert admin.raw(inactive)["stockQuantity"] == 5


def test_giving_units_back_adds_them_and_never_creates_a_product(repository, admin):
    product_id = admin(2)
    unknown = str(uuid.uuid4())

    repository.increment_stock(product_id, 3, NOW)
    repository.increment_stock(unknown, 3, NOW)

    assert admin.raw(product_id)["stockQuantity"] == 5 and isinstance(admin.raw(product_id)["stockQuantity"], Int64)
    assert admin.raw(unknown) is None   # no upsert: releasing a deleted product must not resurrect it


def test_many_requests_for_the_last_units_never_take_more_than_there_are(repository, admin):
    """The race that matters (spec CA-C3.6): 20 clients, 5 units. Exactly 5 win, and the stock ends at 0, never below."""
    product_id = admin(5)
    wins, start = [], threading.Barrier(20)

    def buy():
        start.wait()
        wins.append(MongoProductRepository(MongoClient(URI, tz_aware=True).get_default_database()).try_decrement_stock(product_id, 1, NOW))

    threads = [threading.Thread(target=buy) for _ in range(20)]
    [t.start() for t in threads]
    [t.join() for t in threads]

    assert wins.count(True) == 5 and wins.count(False) == 15
    assert admin.raw(product_id)["stockQuantity"] == 0


def test_reserving_through_the_use_case_is_all_or_nothing_on_the_real_database(repository, admin):
    plenty, scarce = admin(10, name="Plenty"), admin(1, name="Scarce")
    reserve = ReserveStockService(repository, Clock())

    with pytest.raises(BusinessRuleViolation) as raised:
        reserve.execute([StockItem(plenty, 4), StockItem(scarce, 2)])

    assert raised.value.rule_id == "INV-PRODUCT-002"
    assert (admin.raw(plenty)["stockQuantity"], admin.raw(scarce)["stockQuantity"]) == (10, 1)

    lines = reserve.execute([StockItem(plenty, 4), StockItem(scarce, 1)])
    assert [(l.product_name, l.quantity) for l in lines] == [("Plenty", 4), ("Scarce", 1)]
    assert (admin.raw(plenty)["stockQuantity"], admin.raw(scarce)["stockQuantity"]) == (6, 0)


def test_the_service_user_cannot_create_a_collection_or_read_another_database():
    """Annex J: catalog_app writes only in its own database, and only what the service needs."""
    client = MongoClient(URI, tz_aware=True)
    with pytest.raises(Exception, match="not authorized|Unauthorized|requires authentication"):
        client.get_default_database().create_collection("rogue")
    with pytest.raises(Exception, match="not authorized|Unauthorized|requires authentication"):
        client["other_domain"].thing.insert_one({"a": 1})
