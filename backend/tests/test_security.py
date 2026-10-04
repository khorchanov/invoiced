from datetime import timedelta

import jwt
import pytest

from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_is_not_plaintext_and_verifies() -> None:
    hashed = hash_password("s3cret-pass")

    assert hashed != "s3cret-pass"
    assert verify_password("s3cret-pass", hashed)


def test_wrong_password_fails() -> None:
    assert not verify_password("wrong", hash_password("s3cret-pass"))


def test_same_password_gives_different_hashes() -> None:
    assert hash_password("s3cret-pass") != hash_password("s3cret-pass")


def test_token_roundtrip() -> None:
    token = create_access_token("user-123")

    assert decode_access_token(token) == "user-123"


def test_expired_token_is_rejected() -> None:
    token = create_access_token("user-123", expires_delta=timedelta(seconds=-1))

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_tampered_token_is_rejected() -> None:
    token = create_access_token("user-123")

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token[:-2] + "xx")
