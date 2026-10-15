"""Tokens for the tests, signed with a key pair made on the spot: no key file ever enters the repository."""

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

NOW = 1_800_000_000
USER = "11111111-1111-4111-8111-111111111111"

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PUBLIC_PEM = _KEY.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()


def bearer(role: str = "ADMIN", **claims) -> dict:
    payload = {"sub": USER, "role": role, "exp": NOW + 900, **claims}
    return {"Authorization": "Bearer " + jwt.encode(payload, _KEY, algorithm="RS256")}
