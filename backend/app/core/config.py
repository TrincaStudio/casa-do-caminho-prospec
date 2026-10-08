from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    app_name: str = "Casa do Caminho Research"
    public_api_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:5173"
    cors_origins: str = "http://localhost:5173"

    repository_backend: str = "memory"
    auth_required: bool = True
    auth_test_user_id: str = ""

    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"
    brave_search_api_key: str = ""
    firecrawl_api_key: str = ""
    research_mode: str = "mock"

    max_brave_queries_per_research: int = 12
    max_urls_per_research: int = 24
    max_firecrawl_pages_per_research: int = 12
    max_openai_batches_per_research: int = 6
    max_content_chars_per_document: int = 12000
    search_cache_ttl_hours: int = 24
    document_cache_ttl_hours: int = 168
    request_timeout_seconds: float = 30.0
    firecrawl_timeout_seconds: float = 60.0
    external_retry_attempts: int = 3
    worker_poll_seconds: float = 5.0
    worker_job_timeout_seconds: int = 900
    duplicate_window_minutes: int = 30
    rate_limit_research_per_hour: int = 5

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("research_mode")
    @classmethod
    def validate_research_mode(cls, value: str) -> str:
        value = value.lower().strip()
        if value not in {"mock", "live"}:
            raise ValueError("RESEARCH_MODE must be mock or live")
        return value

    @field_validator("repository_backend")
    @classmethod
    def validate_repository_backend(cls, value: str) -> str:
        value = value.lower().strip()
        if value not in {"memory", "supabase"}:
            raise ValueError("REPOSITORY_BACKEND must be memory or supabase")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def live_ready(self) -> bool:
        return bool(self.openai_api_key and self.brave_search_api_key and self.firecrawl_api_key)

    def validate_staging_readiness(self) -> None:
        if self.app_env == "staging":
            missing: list[str] = []
            for key, value in {
                "SUPABASE_URL": self.supabase_url,
                "SUPABASE_ANON_KEY": self.supabase_anon_key,
                "SUPABASE_SERVICE_ROLE_KEY": self.supabase_service_role_key,
                "OPENAI_API_KEY": self.openai_api_key,
                "BRAVE_SEARCH_API_KEY": self.brave_search_api_key,
                "FIRECRAWL_API_KEY": self.firecrawl_api_key,
            }.items():
                if not value:
                    missing.append(key)
            if self.repository_backend != "supabase":
                missing.append("REPOSITORY_BACKEND=supabase")
            if self.research_mode != "live":
                missing.append("RESEARCH_MODE=live")
            if missing:
                raise RuntimeError("Staging configuration missing: " + ", ".join(missing))


settings = Settings()
