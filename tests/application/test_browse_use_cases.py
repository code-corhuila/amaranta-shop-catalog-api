"""Browsing the catalog: the active products, one bounded page at a time, and one product by id."""

import pytest

from catalog.application.errors import ProductNotFoundError
from catalog.application.usecase.browse import GetProductService, ListActiveProductsService
from tests.application.fakes import CAT_TOY, DOG_FOOD, UNKNOWN, FakeProducts, product


@pytest.fixture
def products() -> FakeProducts:
    return FakeProducts(product(DOG_FOOD, "Dog food", stock=5), product(CAT_TOY, "Cat toy", stock=0),
                        product("22222222-2222-4222-8222-222222222222", "Aquarium", stock=2),
                        product("33333333-3333-4333-8333-333333333333", "Hidden", stock=9))


def test_only_the_active_products_are_listed_sorted_by_name(products):
    products.by_id["33333333-3333-4333-8333-333333333333"].is_active = False

    page = ListActiveProductsService(products).execute(page=1, limit=20)

    assert [p.name for p in page.data] == ["Aquarium", "Cat toy", "Dog food"]
    assert page.total == 3 and page.total_pages == 1


def test_a_product_out_of_stock_is_still_listed(products):
    page = ListActiveProductsService(products).execute(page=1, limit=20)

    assert next(p for p in page.data if p.id == CAT_TOY).stock_quantity == 0


def test_the_list_is_bounded_and_says_how_many_pages_there_are(products):
    second = ListActiveProductsService(products).execute(page=2, limit=3)

    assert [p.name for p in second.data] == ["Hidden"] and second.total == 4 and second.total_pages == 2
    assert ListActiveProductsService(products).execute(page=9, limit=3).data == []


@pytest.mark.parametrize("page,limit", [(0, 20), (-1, 20), (1, 0), (1, 101)])
def test_a_page_or_a_limit_out_of_range_is_refused(products, page, limit):
    with pytest.raises(ValueError):
        ListActiveProductsService(products).execute(page=page, limit=limit)


def test_a_product_is_found_by_its_id(products):
    assert GetProductService(products).execute(DOG_FOOD).name == "Dog food"


def test_an_unknown_or_inactive_product_is_not_found(products):
    products.by_id[CAT_TOY].is_active = False

    for missing in (UNKNOWN, CAT_TOY):
        with pytest.raises(ProductNotFoundError):
            GetProductService(products).execute(missing)
