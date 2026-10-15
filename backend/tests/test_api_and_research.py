from fastapi.testclient import TestClient

from app.core.config import settings
from app.repositories.factory import set_repository_for_tests
from app.repositories.memory import MemoryRepository
from app.research.orchestrator import ResearchOrchestrator


def setup_module():
    settings.auth_required = False
    settings.research_mode = "mock"
    settings.repository_backend = "memory"
    settings.cors_origins = "http://localhost:5173,https://casa-do-caminho-staging.netlify.app"


def test_api_requires_auth_when_enabled():
    settings.auth_required = True
    set_repository_for_tests(MemoryRepository())
    from app.main import app

    client = TestClient(app)
    response = client.get("/api/research")
    assert response.status_code == 401
    settings.auth_required = False


def test_cors_preflight_allows_configured_netlify_origin():
    from app.main import app

    client = TestClient(app)
    origin = "https://casa-do-caminho-staging.netlify.app"
    response = client.options(
        "/api/research",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "authorization" in response.headers["access-control-allow-headers"].lower()
    assert "content-type" in response.headers["access-control-allow-headers"].lower()


def test_cors_preflight_rejects_unconfigured_origin():
    from app.main import app

    client = TestClient(app)
    response = client.options(
        "/api/research",
        headers={
            "Origin": "https://unauthorized.example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_create_list_get_and_cancel_research():
    repository = MemoryRepository()
    set_repository_for_tests(repository)
    from app.main import app

    client = TestClient(app)
    payload = {"name": "Empresa Teste", "cnpj": "00.000.000/0001-00", "website": "https://empresa.test"}
    created = client.post("/api/research", json=payload)
    assert created.status_code == 202
    research_id = created.json()["id"]

    listed = client.get("/api/research")
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == research_id

    detail = client.get(f"/api/research/{research_id}")
    assert detail.status_code == 200
    assert detail.json()["status"] == "PENDING"

    cancelled = client.post(f"/api/research/{research_id}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "CANCELLED"


def test_mock_research_pipeline_persists_results():
    repository = MemoryRepository()
    set_repository_for_tests(repository)
    from app.main import app

    client = TestClient(app)
    created = client.post("/api/research", json={"name": "Empresa Mock", "website": "https://empresa.test"})
    research_id = created.json()["id"]

    import asyncio

    asyncio.run(ResearchOrchestrator(repository).run(research_id))
    detail = client.get(f"/api/research/{research_id}").json()
    assert detail["status"] == "COMPLETED"
    assert detail["sections"]
    assert sum(len(section["results"]) for section in detail["sections"]) == 65
    assert detail["usage"]["urls_selected"] > 0


def test_duplicate_research_returns_existing_pending():
    repository = MemoryRepository()
    set_repository_for_tests(repository)
    from app.main import app

    client = TestClient(app)
    payload = {"name": "Empresa Duplicada", "website": "https://duplicada.test"}
    first = client.post("/api/research", json=payload).json()
    second = client.post("/api/research", json=payload).json()
    assert first["id"] == second["id"]
