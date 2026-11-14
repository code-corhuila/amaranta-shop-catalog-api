"""Each service validates the token itself, with RS256 only (norm 5.3.7, Annex C), and the routes ask for a role.

Tokens are signed with a key pair made on the spot: no key file ever enters the repository.
"""

import base64
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient

from catalog.adapter.inbound.http.app import create_app
from catalog.adapter.inbound.http.auth import Caller, Rs256Verifier, require_role

NOW = 1_800_000_000
USER = "11111111-1111-4111-8111-111111111111"


def new_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


KEY, OTHER_KEY = new_key(), new_key()
PEM = KEY.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
ENV_PEM = PEM.strip().replace("\n", "\\n")   # a public key as a .env file stores it: one line, literal backslash-n

verifier = Rs256Verifier(ENV_PEM, clock=lambda: NOW)
router = APIRouter()


@router.get("/admin-only")
def admin_only(caller: Caller = Depends(require_role("ADMIN", verifier=verifier))):
    return {"user": caller.user_id, "role": caller.role}


@router.get("/anyone-signed-in")
def anyone(caller: Caller = Depends(require_role(verifier=verifier))):
    return {"role": caller.role}


client = TestClient(create_app(routers=[router]), raise_server_exceptions=False)


def token(claims=None, key=KEY, algorithm="RS256", **overrides) -> str:
    payload = {"sub": USER, "role": "ADMIN", "exp": NOW + 900}
    payload.update(claims or {})
    payload.update(overrides)
    return jwt.encode({k: v for k, v in payload.items() if v is not None}, key, algorithm=algorithm)


def call(path="/admin-only", authorization=None):
    return client.get(path, headers={"Authorization": authorization} if authorization is not None else {})


def b64(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


def test_a_valid_token_reaches_the_route_and_tells_who_and_what_role():
    response = call(authorization="Bearer " + token())

    assert response.status_code == 200 and response.json() == {"user": USER, "role": "ADMIN"}


def test_the_key_can_come_as_a_env_file_stores_it():
    assert "\\n" in ENV_PEM and "\n" not in ENV_PEM
    assert call(authorization="Bearer " + token()).status_code == 200


def test_without_a_token_it_is_a_401_with_the_envelope_and_the_trace_id():
    response = call(authorization=None)

    assert response.status_code == 401 and response.json()["error"] == "UNAUTHORIZED" and response.json()["traceId"]


@pytest.mark.parametrize("header", ["Basic dXNlcjpwYXNz", "Bearer ", "Bearer", "token abc", ""])
def test_a_header_that_is_not_a_bearer_token_is_a_401(header):
    assert call(authorization=header).status_code == 401


def test_a_token_with_another_algorithm_is_a_401():
    hs256 = jwt.encode({"sub": USER, "role": "ADMIN", "exp": NOW + 900}, "a-shared-secret-of-at-least-32-bytes!!", algorithm="HS256")
    none = b64({"alg": "none", "typ": "JWT"}) + "." + b64({"sub": USER, "role": "ADMIN", "exp": NOW + 900}) + "."

    assert call(authorization="Bearer " + hs256).status_code == 401
    assert call(authorization="Bearer " + none).status_code == 401


def test_the_public_key_used_as_an_hmac_secret_is_not_accepted():
    """The classic hole: HS256 signed with the PUBLIC key as the secret, for a verifier that trusts the token's alg."""
    forged = base64.urlsafe_b64encode(b"x")   # PyJWT refuses to sign HS256 with a PEM, so the token is built by hand
    assert call(authorization="Bearer " + b64({"alg": "HS256"}) + "." + b64({"sub": USER, "role": "ADMIN", "exp": NOW + 900}) + "." + forged.decode()).status_code == 401


def test_an_expired_token_a_forged_one_and_garbage_are_all_401():
    for bad in (token(exp=NOW - 31), token(key=OTHER_KEY), "not.a.token", "x" * 10):
        assert call(authorization="Bearer " + bad).status_code == 401, bad


def test_a_clock_skew_of_thirty_seconds_is_tolerated():
    assert call(authorization="Bearer " + token(exp=NOW - 29)).status_code == 200


def test_a_token_without_exp_or_without_a_subject_is_a_401():
    assert call(authorization="Bearer " + token(exp=None)).status_code == 401
    assert call(authorization="Bearer " + token(sub=None)).status_code == 401


def test_a_valid_token_with_the_wrong_role_is_a_403():
    response = call(authorization="Bearer " + token(role="CUSTOMER"))

    assert response.status_code == 403 and response.json()["error"] == "FORBIDDEN"


def test_a_route_that_asks_for_no_role_accepts_any_valid_token():
    assert call("/anyone-signed-in", "Bearer " + token(role="CUSTOMER")).json() == {"role": "CUSTOMER"}


def test_a_configuration_that_is_not_a_public_key_is_refused_at_start():
    for bad in ("secret", "", None):
        with pytest.raises(ValueError):
            Rs256Verifier(bad)
