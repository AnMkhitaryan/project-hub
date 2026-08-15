from datetime import timedelta

import pytest
from jose.exceptions import ExpiredSignatureError

from app.services.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_verify_password_correct():
    password_hash = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", password_hash)


def test_verify_password_wrong():
    password_hash = hash_password("correct horse battery staple")
    assert not verify_password("wrong password", password_hash)


def test_access_token_round_trip():
    token = create_access_token(user_id=42)
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert "exp" in payload


def test_expired_access_token_raises():
    token = create_access_token(user_id=42, expires_delta=timedelta(seconds=-1))
    with pytest.raises(ExpiredSignatureError):
        decode_access_token(token)
