from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import create_client

from app.core.config import settings
from app.core.schemas import UserContext

bearer = HTTPBearer(auto_error=False)


async def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> UserContext:
    if not settings.auth_required:
        user_id = settings.auth_test_user_id or "00000000-0000-0000-0000-000000000000"
        return UserContext(id=user_id, email="dev@example.local")
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Autenticacao obrigatoria")
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Autenticacao indisponivel")
    try:
        client = create_client(settings.supabase_url, settings.supabase_anon_key)
        response = client.auth.get_user(credentials.credentials)
        user = response.user
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalido ou expirado") from exc
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalido ou expirado")
    return UserContext(id=user.id, email=user.email, access_token=credentials.credentials)
