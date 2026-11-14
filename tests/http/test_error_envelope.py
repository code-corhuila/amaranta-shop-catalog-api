"""Every error, whatever raised it, leaves in the same envelope {error, message, details?, traceId}, and the translation
from a domain error to a status happens in ONE place (norm 5.3, spec section 8.3). The correlation id travels with it."""

import re
import uuid

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import BaseModel

from catalog.adapter.inbound.http.app import create_app
from catalog.adapter.inbound.http.errors import ForbiddenError, UnauthorizedError
from catalog.application.errors import ProductNotFoundError
from catalog.domain.model.errors import BusinessRuleViolation

router = APIRouter()


class Body(BaseModel):
    name: str
    quantity: int


@router.get("/boom/rule")
def rule():
    raise BusinessRuleViolation("INV-PRODUCT-002", "not enough stock")


@router.get("/boom/not-found")
def not_found():
    raise ProductNotFoundError("399d2ea8-1ccb-4193-8255-1b51e331984d")


@router.get("/boom/forbidden")
def forbidden():
    raise ForbiddenError("this action requires the ADMIN role")


@router.get("/boom/unauthorized")
def unauthorized():
    raise UnauthorizedError("the token is invalid or has expired")


@router.get("/boom/unexpected")
def unexpected():
    raise RuntimeError("password authentication failed for user catalog_app at mongo:27017")


@router.get("/products/{product_id}")
def by_id(product_id: uuid.UUID):
    return {"id": str(product_id)}


@router.post("/products")
def create(body: Body):
    return body


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(routers=[router]), raise_server_exceptions=False)


def test_health_answers_without_a_token(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_a_broken_business_rule_is_a_422_that_names_the_rule(client):
    response = client.get("/boom/rule")

    assert response.status_code == 422
    assert response.json()["error"] == "BUSINESS_RULE_VIOLATION"
    assert response.json()["details"] == [{"field": "rule", "message": "INV-PRODUCT-002"}]


def test_a_missing_product_is_a_404(client):
    response = client.get("/boom/not-found")

    assert response.status_code == 404 and response.json()["error"] == "NOT_FOUND"


def test_a_missing_token_is_a_401_and_a_wrong_role_a_403(client):
    assert client.get("/boom/unauthorized").status_code == 401
    assert client.get("/boom/unauthorized").json()["error"] == "UNAUTHORIZED"
    assert client.get("/boom/forbidden").status_code == 403
    assert client.get("/boom/forbidden").json()["error"] == "FORBIDDEN"


def test_an_unexpected_error_is_a_500_with_a_neutral_message_and_no_secrets(client):
    response = client.get("/boom/unexpected")

    assert response.status_code == 500 and response.json()["error"] == "INTERNAL_ERROR"
    assert "password" not in response.text and "mongo" not in response.text
    assert "x-correlation-id" in response.headers


def test_an_id_that_is_not_a_uuid_is_a_400_that_names_the_field(client):
    response = client.get("/products/not-a-uuid")

    assert response.status_code == 400 and response.json()["error"] == "VALIDATION_ERROR"
    assert response.json()["details"][0]["field"] == "product_id"


def test_every_invalid_field_of_a_body_is_named(client):
    response = client.post("/products", json={"quantity": "many"})

    assert response.status_code == 400
    assert {d["field"] for d in response.json()["details"]} == {"name", "quantity"}


def test_malformed_json_is_a_400(client):
    response = client.post("/products", content="{not json", headers={"content-type": "application/json"})

    assert response.status_code == 400 and response.json()["error"] == "VALIDATION_ERROR"


def test_an_unknown_route_is_a_404_with_the_envelope(client):
    response = client.get("/api/v1/nothing")

    assert response.status_code == 404 and response.json()["error"] == "NOT_FOUND"
    assert response.json()["traceId"]


def test_a_wrong_method_is_a_405_with_the_envelope(client):
    response = client.post("/boom/rule")

    assert response.status_code == 405 and "traceId" in response.json()


# correlation (norm 5.3.9) ---------------------------------------------------------------------------------------------

def test_the_trace_id_repeats_the_correlation_id_received_and_the_response_returns_it(client):
    response = client.get("/boom/rule", headers={"X-Correlation-Id": "e2e-saga-1"})

    assert response.headers["x-correlation-id"] == "e2e-saga-1" and response.json()["traceId"] == "e2e-saga-1"


def test_without_a_correlation_id_one_is_generated(client):
    response = client.get("/boom/rule")

    assert re.fullmatch(r"[0-9a-f-]{36}", response.headers["x-correlation-id"])
    assert response.json()["traceId"] == response.headers["x-correlation-id"]


def test_an_absurd_correlation_id_is_replaced_instead_of_echoed(client):
    response = client.get("/boom/rule", headers={"X-Correlation-Id": "x" * 200})

    assert re.fullmatch(r"[0-9a-f-]{36}", response.headers["x-correlation-id"])


# The access line, the log contract and what a log may never hold are in test_access_log.py and test_log_contract.py.
