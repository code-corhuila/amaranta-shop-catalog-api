"""Each service validates the token itself (norm 5.3.7): the gateway only checks that one exists, and a service that
trusted a header set upstream would accept anyone who reaches it through the internal network.

The list of algorithms is closed: RS256 only. A token that declares "none", or HS256 to be checked with the public key
as a secret, is refused instead of being verified with the wrong algorithm. This service holds the PUBLIC key of
amaranta-shop-security and never the private one.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass

import jwt
from cryptography.hazmat.primitives import serialization
from fastapi import Request

from catalog.adapter.inbound.http.errors import ForbiddenError, UnauthorizedError

LEEWAY_SECONDS = 30
_REJECTED = "the token is invalid or has expired"


@dataclass(frozen=True)
class Caller:
    """Who the token says it is: the `sub` and the `role` claims."""

    user_id: str
    role: str


class Rs256Verifier:
    def __init__(self, public_key_pem: str | None, clock: Callable[[], float] = time.time) -> None:
        """The newlines of the key may be the two characters backslash-n, as a .env file stores it."""
        if not public_key_pem or "BEGIN PUBLIC KEY" not in public_key_pem:
            raise ValueError("JWT public key is not a PEM public key")
        try:
            self._key = serialization.load_pem_public_key(public_key_pem.replace("\\n", "\n").encode())
        except ValueError as error:
            raise ValueError("JWT public key cannot be read") from error
        self._clock = clock

    def verify(self, token: str) -> Caller:
        try:
            if jwt.get_unverified_header(token).get("alg") != "RS256":
                raise UnauthorizedError(_REJECTED)
            # Expiry is judged below with the injected clock, so it can be tested without waiting.
            claims = jwt.decode(token, self._key, algorithms=["RS256"], options={"require": ["exp", "sub"], "verify_exp": False})
        except (jwt.PyJWTError, ValueError) as error:
            raise UnauthorizedError(_REJECTED) from error
        if not isinstance(claims["exp"], (int, float)) or self._clock() > claims["exp"] + LEEWAY_SECONDS or not isinstance(claims["sub"], str):
            raise UnauthorizedError(_REJECTED)
        return Caller(user_id=claims["sub"], role=str(claims.get("role", "")))


def require_role(*roles: str, verifier: Rs256Verifier) -> Callable[[Request], Caller]:
    """A FastAPI dependency: a valid token, and, if roles are given, one of them (else 403)."""

    def dependency(request: Request) -> Caller:
        header = request.headers.get("authorization")
        if header is None:
            raise UnauthorizedError("a bearer token is required")
        scheme, _, token = header.partition(" ")
        if scheme != "Bearer" or not token.strip():
            raise UnauthorizedError(_REJECTED)
        caller = verifier.verify(token.strip())
        if roles and caller.role not in roles:
            raise ForbiddenError("this action requires one of the roles: " + ", ".join(roles))
        return caller

    return dependency
