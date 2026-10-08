from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from app.core.enums import ResearchStatus, ResultStatus, SourceType, StepStatus
from app.core.schemas import ResearchDetail, ResearchSummary, UserContext


class Repository(ABC):
    @abstractmethod
    async def create_company(self, company: dict[str, Any], user_id: str) -> str:
        raise NotImplementedError

    @abstractmethod
    async def create_research(
        self,
        company_id: str,
        company: dict[str, Any],
        user_id: str,
        checklist_version: str,
        idempotency_key: str | None,
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    async def find_recent_duplicate(self, company: dict[str, Any], user_id: str, window_minutes: int) -> ResearchSummary | None:
        raise NotImplementedError

    @abstractmethod
    async def list_researches(self, user: UserContext) -> list[ResearchSummary]:
        raise NotImplementedError

    @abstractmethod
    async def get_research(self, research_id: str, user: UserContext | None = None) -> ResearchDetail | None:
        raise NotImplementedError

    @abstractmethod
    async def claim_next_pending(self, worker_id: str) -> ResearchDetail | None:
        raise NotImplementedError

    @abstractmethod
    async def update_research_status(
        self,
        research_id: str,
        status: ResearchStatus,
        error_public: str | None = None,
        error_internal: str | None = None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def cancel_research(self, research_id: str, user: UserContext) -> ResearchStatus:
        raise NotImplementedError

    @abstractmethod
    async def upsert_progress_step(
        self,
        research_id: str,
        key: str,
        title: str,
        status: StepStatus,
        completed_items: int,
        total_items: int,
        message: str | None = None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_cached_search(self, query_hash: str, expires_after: datetime) -> list[dict[str, Any]] | None:
        raise NotImplementedError

    @abstractmethod
    async def save_search_execution(
        self,
        research_id: str,
        group_key: str,
        query: str,
        query_hash: str,
        results: list[dict[str, Any]],
        status: str,
        error: str | None = None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def upsert_source(self, research_id: str, source: dict[str, Any]) -> str:
        raise NotImplementedError

    @abstractmethod
    async def get_cached_document(self, normalized_url: str, expires_after: datetime) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    async def save_document(self, research_id: str, source_id: str, document: dict[str, Any]) -> str:
        raise NotImplementedError

    @abstractmethod
    async def save_evidence(self, research_id: str, source_id: str, document_id: str | None, excerpt: str, metadata: dict[str, Any]) -> str:
        raise NotImplementedError

    @abstractmethod
    async def save_result(
        self,
        research_id: str,
        section_key: str,
        question_key: str,
        question: str,
        status: ResultStatus,
        answer: str,
        summary: str,
        evidence_ids: list[str],
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def increment_usage(self, research_id: str, **increments: int) -> None:
        raise NotImplementedError
