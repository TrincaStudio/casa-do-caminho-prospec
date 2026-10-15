import logging

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError, PyJWKClient

from app.core.config import settings
from app.core.schemas import UserContext

bearer = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)
ASYMMETRIC_ALGORITHMS = {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}
_jwks_clients: dict[str, PyJWKClient] = {}


def _issuer() -> str:
    return f"{settings.supabase_url.rstrip('/')}/auth/v1"


def _jwks_client() -> PyJWKClient:
    url = settings.supabase_jwks_url or f"{_issuer()}/.well-known/jwks.json"
    if url not in _jwks_clients:
        _jwks_clients[url] = PyJWKClient(url)
    return _jwks_clients[url]


def _verify_access_token(token: str) -> dict:
    header = jwt.get_unverified_header(token)
    algorithm = header.get("alg")
    if algorithm == "HS256":
        if not settings.supabase_jwt_secret:
            raise InvalidTokenError("HS256 verification secret is not configured")
        key = settings.supabase_jwt_secret
    elif algorithm in ASYMMETRIC_ALGORITHMS:
        key = _jwks_client().get_signing_key_from_jwt(token).key
    else:
        raise InvalidTokenError("Unsupported JWT algorithm")

    return jwt.decode(
        token,
        key,
        algorithms=[algorithm],
        audience=settings.supabase_jwt_audience,
        issuer=_issuer(),
        options={"require": ["exp", "iss", "aud", "sub"]},
    )


async def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> UserContext:
    if not settings.auth_required:
        user_id = settings.auth_test_user_id or "00000000-0000-0000-0000-000000000000"
        return UserContext(id=user_id, email="dev@example.local")
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticacao obrigatoria")
    if not settings.supabase_url:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Autenticacao indisponivel")
    try:
        claims = _verify_access_token(credentials.credentials)
    except Exception as exc:
        logger.info("Rejected Supabase access token: %s", type(exc).__name__)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalido ou expirado") from exc

    user_id = claims.get("sub")
    if not isinstance(user_id, str) or not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalido ou expirado")
    return UserContext(id=user_id, email=claims.get("email"), access_token=credentials.credentials)
