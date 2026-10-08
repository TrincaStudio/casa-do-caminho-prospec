from app.core.config import settings
from app.repositories.base import Repository
from app.repositories.memory import MemoryRepository
from app.repositories.supabase_repo import SupabaseRepository

_override_repository: Repository | None = None
_repository: Repository | None = None

def get_repository() -> Repository:
    global _repository
    if _override_repository is not None:
        return _override_repository
    if _repository is not None:
        return _repository
    if settings.repository_backend == "supabase":
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required for Supabase repository")
        _repository = SupabaseRepository(settings.supabase_url, settings.supabase_service_role_key)
    else:
        _repository = MemoryRepository()
    return _repository


def set_repository_for_tests(repository: Repository) -> None:
    global _override_repository, _repository
    _override_repository = repository
    _repository = repository
