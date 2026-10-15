import asyncio

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta, timezone

from app.core.auth import current_user
from app.core.checklist import SECTIONS
from app.core.config import settings
from app.core.enums import ResearchStatus, StepStatus
from app.core.schemas import CancelResearchOut, CompanyInput, ResearchDetail, ResearchSummary, UserContext
from app.repositories.factory import get_repository
from app.research.planner import CHECKLIST_VERSION, GROUP_TITLES, create_research_plan

app = FastAPI(title=settings.app_name)
local_worker_task: asyncio.Task | None = None
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)


@app.on_event("startup")
async def startup() -> None:
    global local_worker_task
    settings.validate_staging_readiness()
    if settings.app_env == "development" and settings.repository_backend == "memory":
        from app.worker import main as worker_main

        local_worker_task = asyncio.create_task(worker_main(), name="local-research-worker")


@app.on_event("shutdown")
async def shutdown() -> None:
    if local_worker_task:
        local_worker_task.cancel()
        await asyncio.gather(local_worker_task, return_exceptions=True)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "mode": settings.research_mode,
        "repository": settings.repository_backend,
        "auth_required": settings.auth_required,
    }


@app.get("/api/checklist")
def checklist(user: UserContext = Depends(current_user)) -> list[dict]:
    return SECTIONS


@app.get("/api/research", response_model=list[ResearchSummary])
async def list_research(user: UserContext = Depends(current_user)) -> list[ResearchSummary]:
    return await get_repository().list_researches(user)


@app.post("/api/research", status_code=202, response_model=ResearchSummary)
async def create_research(payload: CompanyInput, user: UserContext = Depends(current_user)) -> ResearchSummary:
    repository = get_repository()
    company = payload.model_dump(exclude={"idempotency_key"})
    recent_researches = await repository.list_researches(user)
    hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    created_last_hour = [item for item in recent_researches if item.created_at and item.created_at >= hour_ago]
    if len(created_last_hour) >= settings.rate_limit_research_per_hour:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Limite de pesquisas por hora atingido")
    duplicate = await repository.find_recent_duplicate(company, user.id, settings.duplicate_window_minutes)
    if duplicate and duplicate.status in {ResearchStatus.PENDING, ResearchStatus.PROCESSING}:
        return duplicate
    company_id = await repository.create_company(company, user.id)
    research_id = await repository.create_research(company_id, company, user.id, CHECKLIST_VERSION, payload.idempotency_key)
    plan = create_research_plan(company)
    for group, questions in plan.groups.items():
        if questions:
            await repository.upsert_progress_step(research_id, group.value, GROUP_TITLES[group], StepStatus.WAITING, 0, len(questions))
    detail = await repository.get_research(research_id, user)
    assert detail is not None
    return ResearchSummary(**detail.model_dump(exclude={"sections", "sources"}))


@app.get("/api/research/{research_id}", response_model=ResearchDetail)
async def get_research(research_id: str, user: UserContext = Depends(current_user)) -> ResearchDetail:
    research = await get_repository().get_research(research_id, user)
    if not research:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pesquisa nao encontrada")
    return research


@app.post("/api/research/{research_id}/cancel", response_model=CancelResearchOut)
async def cancel_research(research_id: str, user: UserContext = Depends(current_user)) -> CancelResearchOut:
    try:
        new_status = await get_repository().cancel_research(research_id, user)
    except KeyError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pesquisa nao encontrada") from exc
    return CancelResearchOut(id=research_id, status=new_status)
