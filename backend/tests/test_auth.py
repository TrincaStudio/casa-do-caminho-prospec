import asyncio
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core import auth
from app.core.auth import current_user
from app.core.config import settings


PROJECT_URL = "https://project.supabase.co"
JWT_SECRET = "test-only-supabase-jwt-secret"


def credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def token(**overrides: object) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "iss": f"{PROJECT_URL}/auth/v1",
        "aud": "authenticated",
        "sub": "user-123",
        "email": "user@example.com",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=10)).timestamp()),
    }
    claims.update(overrides)
    return jwt.encode(claims, JWT_SECRET, algorithm="HS256")


@pytest.fixture(autouse=True)
def auth_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "auth_required", True)
    monkeypatch.setattr(settings, "supabase_url", PROJECT_URL)
    monkeypatch.setattr(settings, "supabase_jwt_secret", JWT_SECRET)
    monkeypatch.setattr(settings, "supabase_jwks_url", "")
    monkeypatch.setattr(settings, "supabase_jwt_audience", "authenticated")
    auth._jwks_clients.clear()


def test_accepts_valid_hs256_token():
    user = asyncio.run(current_user(credentials(token())))

    assert user.id == "user-123"
    assert user.email == "user@example.com"


def test_accepts_valid_rs256_token_from_jwks(monkeypatch: pytest.MonkeyPatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    now = datetime.now(timezone.utc)
    asymmetric_token = jwt.encode(
        {
            "iss": f"{PROJECT_URL}/auth/v1",
            "aud": "authenticated",
            "sub": "user-456",
            "exp": int((now + timedelta(minutes=10)).timestamp()),
        },
        private_key,
        algorithm="RS256",
        headers={"kid": "test-key"},
    )

    class FakeJWKClient:
        def __init__(self, _url: str):
            pass

        def get_signing_key_from_jwt(self, _token: str):
            return type("SigningKey", (), {"key": public_key})()

    monkeypatch.setattr(settings, "supabase_jwt_secret", "")
    monkeypatch.setattr(settings, "supabase_jwks_url", "https://project.supabase.co/auth/v1/.well-known/jwks.json")
    monkeypatch.setattr(auth, "PyJWKClient", FakeJWKClient)
    auth._jwks_clients.clear()

    user = asyncio.run(current_user(credentials(asymmetric_token)))

    assert user.id == "user-456"


def test_rejects_expired_token():
    expired = token(exp=int((datetime.now(timezone.utc) - timedelta(minutes=1)).timestamp()))

    with pytest.raises(HTTPException) as error:
        asyncio.run(current_user(credentials(expired)))

    assert error.value.status_code == 401


def test_rejects_invalid_signature():
    invalid = jwt.encode(
        {"iss": f"{PROJECT_URL}/auth/v1", "aud": "authenticated", "sub": "user-123", "exp": int((datetime.now(timezone.utc) + timedelta(minutes=10)).timestamp())},
        "another-secret",
        algorithm="HS256",
    )

    with pytest.raises(HTTPException) as error:
        asyncio.run(current_user(credentials(invalid)))

    assert error.value.status_code == 401


def test_rejects_token_from_another_project():
    other_project = token(iss="https://another-project.supabase.co/auth/v1")

    with pytest.raises(HTTPException) as error:
        asyncio.run(current_user(credentials(other_project)))

    assert error.value.status_code == 401


def test_rejects_wrong_audience():
    wrong_audience = token(aud="anon")

    with pytest.raises(HTTPException) as error:
        asyncio.run(current_user(credentials(wrong_audience)))

    assert error.value.status_code == 401
