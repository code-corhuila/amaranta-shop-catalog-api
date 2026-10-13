"""The two internal endpoints Sales calls (spec DP-8, section 8.5, step 3). The gateway never publishes them: they need
no token because only the services on the platform network can reach them (spec OD-3). The JSON below is the exact
contract that amaranta-shop-sales-api's CatalogStockHttpAdapter speaks."""

import pytest
from fastapi.testclient import TestClient

from catalog.adapter.inbound.http.app import create_app
from catalog.adapter.inbound.http.internal import internal_router
from catalog.application.usecase.release_stock import ReleaseStockService
from catalog.application.usecase.reserve_stock import ReserveStockService
from tests.application.fakes import CAT_TOY, DOG_FOOD, UNKNOWN, FakeClock, FakeProducts, product


@pytest.fixture
def products() -> FakeProducts:
    return FakeProducts(product(DOG_FOOD, "Dog food 3 kg", 45_000, stock=10), product(CAT_TOY, "Cat toy", 12_500, stock=3))


@pytest.fixture
def client(products) -> TestClient:
    router = internal_router(ReserveStockService(products, FakeClock()), ReleaseStockService(products, FakeClock()))
    return TestClient(create_app(routers=[router]), raise_server_exceptions=False)


def items(*pairs):
    return {"items": [{"productId": product_id, "quantity": quantity} for product_id, quantity in pairs]}


def test_reserving_answers_with_the_lines_sales_will_freeze_in_the_order(client, products):
    response = client.post("/internal/products/reserve-stock", json=items((DOG_FOOD, 2), (CAT_TOY, 1)))

    assert response.status_code == 200
    assert response.json() == {"lines": [
        {"productId": DOG_FOOD, "productName": "Dog food 3 kg", "unitPriceAmount": 45_000, "quantity": 2},
        {"productId": CAT_TOY, "productName": "Cat toy", "unitPriceAmount": 12_500, "quantity": 1}]}
    assert (products.stock_of(DOG_FOOD), products.stock_of(CAT_TOY)) == (8, 2)


def test_a_rule_of_the_catalog_is_a_422_that_names_the_rule_and_takes_nothing(client, products):
    scarce = client.post("/internal/products/reserve-stock", json=items((DOG_FOOD, 1), (CAT_TOY, 4)))
    unknown = client.post("/internal/products/reserve-stock", json=items((UNKNOWN, 1)))

    assert scarce.status_code == 422 and scarce.json()["details"] == [{"field": "rule", "message": "INV-PRODUCT-002"}]
    assert unknown.status_code == 422 and unknown.json()["details"][0]["message"] == "PRODUCT_NOT_FOUND"
    assert (products.stock_of(DOG_FOOD), products.stock_of(CAT_TOY)) == (10, 3)


def test_the_same_product_twice_in_one_request_is_a_422(client):
    response = client.post("/internal/products/reserve-stock", json=items((DOG_FOOD, 1), (DOG_FOOD, 2)))

    assert response.status_code == 422 and response.json()["details"][0]["message"] == "INV-STOCK-002"


@pytest.mark.parametrize("body", [
    {"items": []},
    {"items": [{"productId": "not-a-uuid", "quantity": 1}]},
    {"items": [{"productId": DOG_FOOD, "quantity": 0}]},
    {"items": [{"productId": DOG_FOOD, "quantity": 1.5}]},
    {"items": [{"productId": DOG_FOOD, "quantity": "2"}]},
    {"items": [{"quantity": 1}]},
    {},
])
def test_a_body_with_the_wrong_shape_is_a_400_and_takes_nothing(client, products, body):
    response = client.post("/internal/products/reserve-stock", json=body)

    assert response.status_code == 400 and response.json()["error"] == "VALIDATION_ERROR"
    assert products.stock_of(DOG_FOOD) == 10


def test_releasing_is_a_204_and_gives_the_units_back(client, products):
    client.post("/internal/products/reserve-stock", json=items((DOG_FOOD, 4)))

    response = client.post("/internal/products/release-stock", json=items((DOG_FOOD, 4)))

    assert response.status_code == 204 and response.content == b""
    assert products.stock_of(DOG_FOOD) == 10


def test_releasing_a_product_that_no_longer_exists_is_still_a_204(client):
    assert client.post("/internal/products/release-stock", json=items((UNKNOWN, 1))).status_code == 204


def test_the_internal_routes_need_no_token(client):
    assert client.post("/internal/products/release-stock", json=items((CAT_TOY, 1))).status_code == 204
