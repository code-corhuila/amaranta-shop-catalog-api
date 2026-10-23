"""The administration routes: ADMIN only (monolith: AdminCatalogController behind JwtAuthGuard and RolesGuard)."""

import pytest
from fastapi.testclient import TestClient

from catalog.adapter.inbound.http.admin import admin_router
from catalog.adapter.inbound.http.app import create_app
from catalog.adapter.inbound.http.auth import Rs256Verifier
from catalog.application.usecase.admin import build_admin_ports
from tests.application.fakes import DOG_FOOD, UNKNOWN, FakeClock, FakeProducts, SequentialIds, product
from tests.http.signing import NOW, PUBLIC_PEM, bearer

BASE = "/api/v1/admin/products"
NEW = {"sku": "TOY-009", "name": "Rope toy", "description": "A rope.", "category": "TOYS", "price": 9_000, "stockQuantity": 4,
       "imageUrl": "https://example.test/rope.png"}


@pytest.fixture
def products() -> FakeProducts:
    return FakeProducts(product(DOG_FOOD, "Dog food 3 kg", 45_000, stock=10, sku="FOOD-001"))


@pytest.fixture
def client(products) -> TestClient:
    router = admin_router(build_admin_ports(products, FakeClock(), SequentialIds()), Rs256Verifier(PUBLIC_PEM, clock=lambda: NOW))
    return TestClient(create_app(routers=[router]), raise_server_exceptions=False)


def test_every_admin_route_needs_a_token_and_the_admin_role(client):
    for method, path in [("get", BASE), ("post", BASE), ("patch", f"{BASE}/{DOG_FOOD}"), ("delete", f"{BASE}/{DOG_FOOD}"),
                         ("post", f"{BASE}/{DOG_FOOD}/activate")]:
        assert getattr(client, method)(path).status_code == 401, (method, path)
        assert getattr(client, method)(path, headers=bearer("CUSTOMER")).status_code == 403, (method, path)


def test_the_admin_creates_a_product_and_gets_it_back_with_an_id(client, products):
    response = client.post(BASE, json=NEW, headers=bearer())

    assert response.status_code == 201
    body = response.json()
    assert (body["sku"], body["price"], body["stockQuantity"], body["isActive"]) == ("TOY-009", 9_000, 4, True)
    assert response.headers["location"] == f"{BASE}/{body['id']}" and products.find_by_id(body["id"]) is not None


def test_a_duplicate_sku_is_a_422_and_an_invalid_product_is_a_400_or_a_422(client):
    assert client.post(BASE, json={**NEW, "sku": "FOOD-001"}, headers=bearer()).json()["details"][0]["message"] == "SKU_ALREADY_EXISTS"
    assert client.post(BASE, json={**NEW, "price": 0}, headers=bearer()).status_code == 400
    assert client.post(BASE, json={**NEW, "price": 10.5}, headers=bearer()).status_code == 400
    assert client.post(BASE, json={**NEW, "stockQuantity": -1}, headers=bearer()).status_code == 400
    assert client.post(BASE, json={**NEW, "category": "PETS"}, headers=bearer()).status_code == 400
    assert client.post(BASE, json={**{k: v for k, v in NEW.items() if k != "name"}}, headers=bearer()).status_code == 400


def test_every_invalid_field_is_named(client):
    response = client.post(BASE, json={**NEW, "price": 0, "name": "", "category": "PETS"}, headers=bearer())

    assert {d["field"] for d in response.json()["details"]} == {"price", "name", "category"}


def test_the_admin_edits_only_the_fields_given(client):
    response = client.patch(f"{BASE}/{DOG_FOOD}", json={"price": 50_000}, headers=bearer())

    assert response.status_code == 200 and (response.json()["price"], response.json()["name"]) == (50_000, "Dog food 3 kg")


def test_an_edit_without_any_field_is_a_400(client):
    assert client.patch(f"{BASE}/{DOG_FOOD}", json={}, headers=bearer()).status_code == 400


def test_the_stock_is_set_exactly(client, products):
    assert client.patch(f"{BASE}/{DOG_FOOD}/stock", json={"stockQuantity": 0}, headers=bearer()).json()["stockQuantity"] == 0
    assert client.patch(f"{BASE}/{DOG_FOOD}/stock", json={"stockQuantity": -1}, headers=bearer()).status_code == 400
    assert client.patch(f"{BASE}/{DOG_FOOD}/stock", json={"stockQuantity": 2.5}, headers=bearer()).status_code == 400
    assert products.stock_of(DOG_FOOD) == 0


def test_a_product_is_deactivated_and_activated_again(client):
    assert client.post(f"{BASE}/{DOG_FOOD}/deactivate", headers=bearer()).json()["isActive"] is False
    assert client.post(f"{BASE}/{DOG_FOOD}/activate", headers=bearer()).json()["isActive"] is True


def test_deleting_is_a_204_and_the_product_is_gone(client, products):
    assert client.delete(f"{BASE}/{DOG_FOOD}", headers=bearer()).status_code == 204
    assert products.find_by_id(DOG_FOOD) is None


def test_acting_on_a_product_that_does_not_exist_is_a_404(client):
    for response in (client.patch(f"{BASE}/{UNKNOWN}", json={"price": 1_000}, headers=bearer()),
                     client.patch(f"{BASE}/{UNKNOWN}/stock", json={"stockQuantity": 1}, headers=bearer()),
                     client.post(f"{BASE}/{UNKNOWN}/activate", headers=bearer()),
                     client.delete(f"{BASE}/{UNKNOWN}", headers=bearer())):
        assert response.status_code == 404, response.request.url


def test_the_admin_list_shows_inactive_products_too_and_is_bounded(client):
    client.post(f"{BASE}/{DOG_FOOD}/deactivate", headers=bearer())

    response = client.get(BASE, headers=bearer())

    assert response.json()["data"][0]["isActive"] is False and response.json()["meta"]["total"] == 1
    assert client.get(BASE, params={"limit": 101}, headers=bearer()).status_code == 400
