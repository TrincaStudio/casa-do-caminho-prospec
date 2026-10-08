from __future__ import annotations

import hashlib
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from app.core.enums import ResearchStatus, ResultStatus, SourceType, StepStatus
from app.core.checklist import SECTIONS
from app.core.schemas import (
    EvidenceRecord,
    ProgressStep,
    ResearchDetail,
    ResearchSummary,
    ResearchUsage,
    SourceRecord,
    UserContext,
)
from app.repositories.base import Repository

SECTION_TITLES = {section["key"]: section["title"] for section in SECTIONS}

def now() -> datetime:
    return datetime.now(timezone.utc)


class MemoryRepository(Repository):
    def __init__(self) -> None:
        self.companies: dict[str, dict[str, Any]] = {}
        self.researches: dict[str, dict[str, Any]] = {}
        self.progress: dict[str, dict[str, dict[str, Any]]] = {}
        self.searches: list[dict[str, Any]] = []
        self.sources: dict[str, dict[str, Any]] = {}
        self.documents: dict[str, dict[str, Any]] = {}
        self.evidences: dict[str, dict[str, Any]] = {}
        self.results: dict[str, dict[str, Any]] = {}
        self.result_evidences: dict[str, list[str]] = {}

    async def create_company(self, company: dict[str, Any], user_id: str) -> str:
        key = (company.get("cnpj") or company.get("website") or company["name"]).lower()
        for existing_id, existing in self.companies.items():
            if existing["owner_user_id"] == user_id and existing["dedupe_key"] == key:
                return existing_id
        company_id = str(uuid4())
        self.companies[company_id] = {**company, "id": company_id, "owner_user_id": user_id, "dedupe_key": key, "created_at": now()}
        return company_id

    async def create_research(
        self,
        company_id: str,
        company: dict[str, Any],
        user_id: str,
        checklist_version: str,
        idempotency_key: str | None,
    ) -> str:
        if idempotency_key:
            for research_id, row in self.researches.items():
                if row["owner_user_id"] == user_id and row.get("idempotency_key") == idempotency_key:
                    return research_id
        research_id = str(uuid4())
        timestamp = now()
        self.researches[research_id] = {
            "id": research_id,
            "company_id": company_id,
            "company": deepcopy(company),
            "owner_user_id": user_id,
            "status": ResearchStatus.PENDING,
            "checklist_version": checklist_version,
            "idempotency_key": idempotency_key,
            "usage": ResearchUsage().model_dump(),
            "error_public": None,
            "error_internal": None,
            "created_at": timestamp,
            "updated_at": timestamp,
            "completed_at": None,
            "locked_by": None,
        }
        self.progress[research_id] = {}
        return research_id

    async def find_recent_duplicate(self, company: dict[str, Any], user_id: str, window_minutes: int) -> ResearchSummary | None:
        threshold = now() - timedelta(minutes=window_minutes)
        company_key = (company.get("cnpj") or company.get("website") or company["name"]).lower()
        for row in sorted(self.researches.values(), key=lambda item: item["created_at"], reverse=True):
            existing_key = (row["company"].get("cnpj") or row["company"].get("website") or row["company"]["name"]).lower()
            if row["owner_user_id"] == user_id and existing_key == company_key and row["created_at"] >= threshold:
                if row["status"] in {ResearchStatus.PENDING, ResearchStatus.PROCESSING, ResearchStatus.COMPLETED, ResearchStatus.COMPLETED_WITH_WARNINGS}:
                    return self._summary(row)
        return None

    async def list_researches(self, user: UserContext) -> list[ResearchSummary]:
        rows = [row for row in self.researches.values() if row["owner_user_id"] == user.id]
        return [self._summary(row) for row in sorted(rows, key=lambda item: item["created_at"], reverse=True)]

    async def get_research(self, research_id: str, user: UserContext | None = None) -> ResearchDetail | None:
        row = self.researches.get(research_id)
        if not row or (user and row["owner_user_id"] != user.id):
            return None
        detail = self._detail(row)
        return detail

    async def claim_next_pending(self, worker_id: str) -> ResearchDetail | None:
        for row in sorted(self.researches.values(), key=lambda item: item["created_at"]):
            if row["status"] == ResearchStatus.PENDING:
                row["status"] = ResearchStatus.PROCESSING
                row["locked_by"] = worker_id
                row["updated_at"] = now()
                return self._detail(row)
        return None

    async def update_research_status(
        self,
        research_id: str,
        status: ResearchStatus,
        error_public: str | None = None,
        error_internal: str | None = None,
    ) -> None:
        row = self.researches[research_id]
        row["status"] = status
        row["error_public"] = error_public
        row["error_internal"] = error_internal
        row["updated_at"] = now()
        if status in {ResearchStatus.COMPLETED, ResearchStatus.COMPLETED_WITH_WARNINGS, ResearchStatus.FAILED, ResearchStatus.CANCELLED}:
            row["completed_at"] = now()

    async def cancel_research(self, research_id: str, user: UserContext) -> ResearchStatus:
        row = self.researches.get(research_id)
        if not row or row["owner_user_id"] != user.id:
            raise KeyError(research_id)
        if row["status"] in {ResearchStatus.COMPLETED, ResearchStatus.COMPLETED_WITH_WARNINGS, ResearchStatus.FAILED}:
            return row["status"]
        row["status"] = ResearchStatus.CANCELLED
        row["updated_at"] = now()
        row["completed_at"] = now()
        return ResearchStatus.CANCELLED

    async def upsert_progress_step(self, research_id: str, key: str, title: str, status: StepStatus, completed_items: int, total_items: int, message: str | None = None) -> None:
        self.progress.setdefault(research_id, {})[key] = {
            "key": key,
            "title": title,
            "status": status,
            "completed_items": completed_items,
            "total_items": total_items,
            "message": message,
        }

    async def get_cached_search(self, query_hash: str, expires_after: datetime) -> list[dict[str, Any]] | None:
        rows = [row for row in self.searches if row["query_hash"] == query_hash and row["created_at"] >= expires_after and row["status"] == "COMPLETED"]
        return deepcopy(rows[-1]["results"]) if rows else None

    async def save_search_execution(self, research_id: str, group_key: str, query: str, query_hash: str, results: list[dict[str, Any]], status: str, error: str | None = None) -> None:
        self.searches.append(
            {
                "id": str(uuid4()),
                "research_id": research_id,
                "group_key": group_key,
                "query": query,
                "query_hash": query_hash,
                "results": deepcopy(results),
                "status": status,
                "error": error,
                "created_at": now(),
            }
        )

    async def upsert_source(self, research_id: str, source: dict[str, Any]) -> str:
        for source_id, existing in self.sources.items():
            if existing["research_id"] == research_id and existing["normalized_url"] == source["normalized_url"]:
                existing.update(source)
                return source_id
        source_id = str(uuid4())
        self.sources[source_id] = {**source, "id": source_id, "research_id": research_id, "accessed_at": now()}
        return source_id

    async def get_cached_document(self, normalized_url: str, expires_after: datetime) -> dict[str, Any] | None:
        for document in self.documents.values():
            if document["normalized_url"] == normalized_url and document["accessed_at"] >= expires_after:
                return deepcopy(document)
        return None

    async def save_document(self, research_id: str, source_id: str, document: dict[str, Any]) -> str:
        document_id = str(uuid4())
        self.documents[document_id] = {**document, "id": document_id, "research_id": research_id, "source_id": source_id, "accessed_at": now()}
        return document_id

    async def save_evidence(self, research_id: str, source_id: str, document_id: str | None, excerpt: str, metadata: dict[str, Any]) -> str:
        fingerprint = hashlib.sha256(f"{source_id}:{excerpt[:300]}".encode()).hexdigest()
        for evidence_id, existing in self.evidences.items():
            if existing["research_id"] == research_id and existing["fingerprint"] == fingerprint:
                return evidence_id
        evidence_id = str(uuid4())
        self.evidences[evidence_id] = {
            "id": evidence_id,
            "research_id": research_id,
            "source_id": source_id,
            "document_id": document_id,
            "excerpt": excerpt,
            "metadata": metadata,
            "fingerprint": fingerprint,
            "created_at": now(),
        }
        return evidence_id

    async def save_result(self, research_id: str, section_key: str, question_key: str, question: str, status: ResultStatus, answer: str, summary: str, evidence_ids: list[str]) -> None:
        key = f"{research_id}:{question_key}"
        result_id = self.results.get(key, {}).get("id", str(uuid4()))
        self.results[key] = {
            "id": result_id,
            "research_id": research_id,
            "section_key": section_key,
            "question_key": question_key,
            "question": question,
            "status": status,
            "answer": answer,
            "summary": summary,
            "created_at": now(),
        }
        self.result_evidences[result_id] = list(dict.fromkeys(evidence_ids))

    async def increment_usage(self, research_id: str, **increments: int) -> None:
        usage = self.researches[research_id]["usage"]
        for key, amount in increments.items():
            usage[key] = int(usage.get(key, 0)) + int(amount)

    def _summary(self, row: dict[str, Any]) -> ResearchSummary:
        progress = [ProgressStep(**step) for step in self.progress.get(row["id"], {}).values()]
        return ResearchSummary(
            id=row["id"],
            company_id=row["company_id"],
            company=row["company"],
            status=row["status"],
            checklist_version=row["checklist_version"],
            progress=progress,
            usage=ResearchUsage(**row["usage"]),
            error_public=row.get("error_public"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
            completed_at=row.get("completed_at"),
        )

    def _detail(self, row: dict[str, Any]) -> ResearchDetail:
        summary = self._summary(row)
        sources = {
            source_id: SourceRecord(
                id=source_id,
                research_id=source["research_id"],
                url=source["url"],
                normalized_url=source["normalized_url"],
                title=source.get("title"),
                domain=source.get("domain"),
                source_type=source.get("source_type", SourceType.OTHER),
                description=source.get("description"),
                accessed_at=source.get("accessed_at"),
                metadata=source.get("metadata") or {},
            )
            for source_id, source in self.sources.items()
            if source["research_id"] == row["id"]
        }
        evidences = {
            evidence_id: EvidenceRecord(
                id=evidence_id,
                research_id=evidence["research_id"],
                source_id=evidence["source_id"],
                document_id=evidence.get("document_id"),
                excerpt=evidence["excerpt"],
                metadata=evidence.get("metadata") or {},
                source=sources.get(evidence["source_id"]),
            )
            for evidence_id, evidence in self.evidences.items()
            if evidence["research_id"] == row["id"]
        }
        sections: dict[str, dict[str, Any]] = {}
        for result in self.results.values():
            if result["research_id"] != row["id"]:
                continue
            section = sections.setdefault(result["section_key"], {"key": result["section_key"], "title": SECTION_TITLES.get(result["section_key"], result["section_key"]), "results": []})
            result_evidences = [evidences[eid] for eid in self.result_evidences.get(result["id"], []) if eid in evidences]
            section["results"].append({**result, "evidences": [item.model_dump(mode="json") for item in result_evidences]})
        return ResearchDetail(**summary.model_dump(), sections=list(sections.values()), sources=list(sources.values()))
