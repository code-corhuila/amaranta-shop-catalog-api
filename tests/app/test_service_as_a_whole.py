"""The service as a whole, over HTTP, with the real filters, handlers and routes wired by the composition root. These are
the checks the teacher will make from outside (Annex C, "Como se verifica"), run here first. The database is the only
double: the real one is proved in tests/integration."""

import pytest
from fastapi.testclient import TestClient

from apps.api.composition import build_app
from apps.api.settings import Settings
from tests.application.fakes import CAT_TOY, DOG_FOOD, FakeClock, FakeProducts, SequentialIds, product
from tests.http.signing import NOW, PUBLIC_PEM, bearer


@pytest.fixture
def products() -> FakeProducts:
    return FakeProducts(product(DOG_FOOD, "Dog food 3 kg", 45_000, stock=10), product(CAT_TOY, "Cat toy", 12_500, stock=3))


@pytest.fixture
def client(products) -> TestClient:
    settings = Settings.from_env({"MONGODB_URI": "unused", "JWT_PUBLIC_KEY": PUBLIC_PEM.replace("\n", "\\n")})
    app = build_app(settings, products=products, clock=FakeClock(), ids=SequentialIds(), time_source=lambda: NOW)
    return TestClient(app, raise_server_exceptions=False)


def test_health_needs_no_token(client):
    assert client.get("/health").status_code == 200


def test_a_visitor_browses_the_shop_without_an_account(client):
    response = client.get("/api/v1/products")

    assert response.status_code == 200 and [p["name"] for p in response.json()["data"]] == ["Cat toy", "Dog food 3 kg"]


def test_the_admin_routes_are_closed_to_everybody_but_an_admin(client):
    assert client.get("/api/v1/admin/products").status_code == 401
    assert client.get("/api/v1/admin/products", headers=bearer("CUSTOMER")).status_code == 403
    assert client.get("/api/v1/admin/products", headers=bearer("ADMIN")).status_code == 200


def test_an_expired_token_is_a_401_and_the_envelope_repeats_the_correlation_id(client):
    response = client.get("/api/v1/admin/products", headers={**bearer("ADMIN", exp=NOW - 3_600), "X-Correlation-Id": "e2e-1"})

    assert response.status_code == 401 and response.json()["traceId"] == "e2e-1"


def test_an_unknown_route_is_a_404_with_the_envelope(client):
    assert client.get("/api/v1/nothing").json()["error"] == "NOT_FOUND"


def test_sales_reserves_and_releases_through_the_internal_routes(client, products):
    body = {"items": [{"productId": DOG_FOOD, "quantity": 4}]}

    reserved = client.post("/internal/products/reserve-stock", json=body)
    assert reserved.status_code == 200 and reserved.json()["lines"][0]["unitPriceAmount"] == 45_000
    assert products.stock_of(DOG_FOOD) == 6

    assert client.post("/internal/products/release-stock", json=body).status_code == 204
    assert products.stock_of(DOG_FOOD) == 10


def test_what_the_shop_shows_follows_what_the_admin_changes(client):
    client.post("/api/v1/admin/products/" + DOG_FOOD + "/deactivate", headers=bearer("ADMIN"))

    assert [p["id"] for p in client.get("/api/v1/products").json()["data"]] == [CAT_TOY]
