"""The public side of the catalog (spec: buying does not require an account, so browsing cannot either)."""

import pytest
from fastapi.testclient import TestClient

from catalog.adapter.inbound.http.app import create_app
from catalog.adapter.inbound.http.public import public_router
from catalog.application.usecase.browse import GetProductService, ListActiveProductsService
from tests.application.fakes import CAT_TOY, DOG_FOOD, UNKNOWN, FakeProducts, product


@pytest.fixture
def client() -> TestClient:
    products = FakeProducts(product(DOG_FOOD, "Dog food 3 kg", price=189_000, stock=24), product(CAT_TOY, "Cat toy", price=8_500, stock=0))
    router = public_router(ListActiveProductsService(products), GetProductService(products))
    return TestClient(create_app(routers=[router]), raise_server_exceptions=False)


def test_anybody_can_list_the_products_without_a_token(client):
    response = client.get("/api/v1/products")

    assert response.status_code == 200
    assert response.json()["meta"] == {"page": 1, "limit": 20, "total": 2, "totalPages": 1}
    assert [p["name"] for p in response.json()["data"]] == ["Cat toy", "Dog food 3 kg"]


def test_a_product_is_shown_with_the_fields_the_shop_page_needs(client):
    dog_food = next(p for p in client.get("/api/v1/products").json()["data"] if p["id"] == DOG_FOOD)

    assert dog_food == {"id": DOG_FOOD, "sku": "SKU-399d", "name": "Dog food 3 kg", "description": "", "category": "FOOD",
                        "price": 189_000, "priceFormatted": "$ 189.000", "stockQuantity": 24, "inStock": True,
                        "imageUrl": "https://example.test/a.png"}


def test_a_product_without_stock_says_so(client):
    cat_toy = next(p for p in client.get("/api/v1/products").json()["data"] if p["id"] == CAT_TOY)

    assert cat_toy["inStock"] is False and cat_toy["stockQuantity"] == 0


def test_the_list_is_bounded_by_the_page_and_the_limit_asked_for(client):
    response = client.get("/api/v1/products", params={"page": 2, "limit": 1})

    assert [p["name"] for p in response.json()["data"]] == ["Dog food 3 kg"]
    assert response.json()["meta"]["totalPages"] == 2


@pytest.mark.parametrize("params", [{"page": 0}, {"limit": 0}, {"limit": 101}, {"limit": "many"}, {"page": "x"}])
def test_a_page_or_a_limit_out_of_range_is_a_400_that_names_the_field(client, params):
    response = client.get("/api/v1/products", params=params)

    assert response.status_code == 400 and response.json()["error"] == "VALIDATION_ERROR"
    assert response.json()["details"][0]["field"] in {"page", "limit"}


def test_one_product_by_id(client):
    assert client.get(f"/api/v1/products/{DOG_FOOD}").json()["name"] == "Dog food 3 kg"


def test_an_unknown_product_is_404_and_an_id_that_is_not_a_uuid_is_400(client):
    assert client.get(f"/api/v1/products/{UNKNOWN}").status_code == 404
    assert client.get("/api/v1/products/not-a-uuid").status_code == 400
