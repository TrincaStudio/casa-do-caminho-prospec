from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from supabase import Client, create_client

from app.core.checklist import SECTIONS
from app.core.enums import ResearchStatus, ResultStatus, SourceType, StepStatus
from app.core.schemas import EvidenceRecord, ProgressStep, ResearchDetail, ResearchSummary, ResearchUsage, SourceRecord, UserContext
from app.repositories.base import Repository

SECTION_TITLES = {section["key"]: section["title"] for section in SECTIONS}

def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SupabaseRepository(Repository):
    def __init__(self, url: str, service_role_key: str) -> None:
        self.client: Client = create_client(url, service_role_key)

    async def create_company(self, company: dict[str, Any], user_id: str) -> str:
        dedupe_key = (company.get("cnpj") or company.get("website") or company["name"]).lower()
        existing = (
            self.client.table("companies")
            .select("id")
            .eq("owner_user_id", user_id)
            .eq("dedupe_key", dedupe_key)
            .limit(1)
            .execute()
            .data
        )
        if existing:
            return existing[0]["id"]
        data = {
            "owner_user_id": user_id,
            "name": company["name"],
            "cnpj": company.get("cnpj"),
            "website": company.get("website"),
            "dedupe_key": dedupe_key,
        }
        return self.client.table("companies").insert(data).execute().data[0]["id"]

    async def create_research(self, company_id: str, company: dict[str, Any], user_id: str, checklist_version: str, idempotency_key: str | None) -> str:
        if idempotency_key:
            existing = (
                self.client.table("researches")
                .select("id")
                .eq("owner_user_id", user_id)
                .eq("idempotency_key", idempotency_key)
                .limit(1)
                .execute()
                .data
            )
            if existing:
                return existing[0]["id"]
        row = {
            "owner_user_id": user_id,
            "company_id": company_id,
            "company_snapshot": company,
            "status": ResearchStatus.PENDING.value,
            "checklist_version": checklist_version,
            "idempotency_key": idempotency_key,
            "usage": ResearchUsage().model_dump(),
        }
        return self.client.table("researches").insert(row).execute().data[0]["id"]

    async def find_recent_duplicate(self, company: dict[str, Any], user_id: str, window_minutes: int) -> ResearchSummary | None:
        existing_key = (company.get("cnpj") or company.get("website") or company["name"]).lower()
        rows = (
            self.client.table("researches")
            .select("*, companies!inner(dedupe_key)")
            .eq("owner_user_id", user_id)
            .eq("companies.dedupe_key", existing_key)
            .in_("status", [ResearchStatus.PENDING.value, ResearchStatus.PROCESSING.value, ResearchStatus.COMPLETED.value, ResearchStatus.COMPLETED_WITH_WARNINGS.value])
            .order("created_at", desc=True)
            .limit(1)
            .execute()
            .data
        )
        return await self.get_research(rows[0]["id"]) if rows else None

    async def list_researches(self, user: UserContext) -> list[ResearchSummary]:
        rows = (
            self.client.table("researches")
            .select("*")
            .eq("owner_user_id", user.id)
            .order("created_at", desc=True)
            .execute()
            .data
        )
        return [await self._summary(row) for row in rows]

    async def get_research(self, research_id: str, user: UserContext | None = None) -> ResearchDetail | None:
        query = self.client.table("researches").select("*").eq("id", research_id)
        if user:
            query = query.eq("owner_user_id", user.id)
        rows = query.limit(1).execute().data
        if not rows:
            return None
        return await self._detail(rows[0])

    async def claim_next_pending(self, worker_id: str) -> ResearchDetail | None:
        rows = (
            self.client.table("researches")
            .select("*")
            .eq("status", ResearchStatus.PENDING.value)
            .order("created_at")
            .limit(1)
            .execute()
            .data
        )
        if not rows:
            return None
        row = rows[0]
        updated = (
            self.client.table("researches")
            .update({"status": ResearchStatus.PROCESSING.value, "locked_by": worker_id, "locked_at": utcnow_iso(), "updated_at": utcnow_iso()})
            .eq("id", row["id"])
            .eq("status", ResearchStatus.PENDING.value)
            .execute()
            .data
        )
        return await self._detail(updated[0]) if updated else None

    async def update_research_status(self, research_id: str, status: ResearchStatus, error_public: str | None = None, error_internal: str | None = None) -> None:
        row = {"status": status.value, "error_public": error_public, "error_internal": error_internal, "updated_at": utcnow_iso()}
        if status in {ResearchStatus.COMPLETED, ResearchStatus.COMPLETED_WITH_WARNINGS, ResearchStatus.FAILED, ResearchStatus.CANCELLED}:
            row["completed_at"] = utcnow_iso()
        self.client.table("researches").update(row).eq("id", research_id).execute()

    async def cancel_research(self, research_id: str, user: UserContext) -> ResearchStatus:
        current = self.client.table("researches").select("status").eq("id", research_id).eq("owner_user_id", user.id).limit(1).execute().data
        if not current:
            raise KeyError(research_id)
        if current[0]["status"] in {ResearchStatus.COMPLETED.value, ResearchStatus.COMPLETED_WITH_WARNINGS.value, ResearchStatus.FAILED.value}:
            return ResearchStatus(current[0]["status"])
        self.client.table("researches").update({"status": ResearchStatus.CANCELLED.value, "completed_at": utcnow_iso(), "updated_at": utcnow_iso()}).eq("id", research_id).execute()
        return ResearchStatus.CANCELLED

    async def upsert_progress_step(self, research_id: str, key: str, title: str, status: StepStatus, completed_items: int, total_items: int, message: str | None = None) -> None:
        self.client.table("research_progress").upsert(
            {
                "research_id": research_id,
                "step_key": key,
                "title": title,
                "status": status.value,
                "completed_items": completed_items,
                "total_items": total_items,
                "message": message,
                "updated_at": utcnow_iso(),
            },
            on_conflict="research_id,step_key",
        ).execute()

    async def get_cached_search(self, query_hash: str, expires_after: datetime) -> list[dict[str, Any]] | None:
        rows = (
            self.client.table("search_executions")
            .select("results")
            .eq("query_hash", query_hash)
            .eq("status", "COMPLETED")
            .gte("created_at", expires_after.isoformat())
            .order("created_at", desc=True)
            .limit(1)
            .execute()
            .data
        )
        return rows[0]["results"] if rows else None

    async def save_search_execution(self, research_id: str, group_key: str, query: str, query_hash: str, results: list[dict[str, Any]], status: str, error: str | None = None) -> None:
        self.client.table("search_executions").insert(
            {"research_id": research_id, "group_key": group_key, "query": query, "query_hash": query_hash, "results": results, "status": status, "error": error}
        ).execute()

    async def upsert_source(self, research_id: str, source: dict[str, Any]) -> str:
        row = {
            "research_id": research_id,
            "url": source["url"],
            "normalized_url": source["normalized_url"],
            "title": source.get("title"),
            "domain": source.get("domain"),
            "source_type": str(source.get("source_type", SourceType.OTHER)),
            "description": source.get("description"),
            "metadata": source.get("metadata") or {},
            "accessed_at": utcnow_iso(),
        }
        rows = self.client.table("sources").upsert(row, on_conflict="research_id,normalized_url").execute().data
        return rows[0]["id"]

    async def get_cached_document(self, normalized_url: str, expires_after: datetime) -> dict[str, Any] | None:
        rows = (
            self.client.table("documents")
            .select("*")
            .eq("normalized_url", normalized_url)
            .gte("accessed_at", expires_after.isoformat())
            .order("accessed_at", desc=True)
            .limit(1)
            .execute()
            .data
        )
        return rows[0] if rows else None

    async def save_document(self, research_id: str, source_id: str, document: dict[str, Any]) -> str:
        row = {
            "research_id": research_id,
            "source_id": source_id,
            "url": document["url"],
            "normalized_url": document["normalized_url"],
            "content": document.get("content", ""),
            "content_hash": document.get("content_hash"),
            "metadata": document.get("metadata") or {},
            "accessed_at": utcnow_iso(),
        }
        return self.client.table("documents").insert(row).execute().data[0]["id"]

    async def save_evidence(self, research_id: str, source_id: str, document_id: str | None, excerpt: str, metadata: dict[str, Any]) -> str:
        fingerprint = hashlib.sha256(f"{source_id}:{excerpt[:300]}".encode()).hexdigest()
        row = {
            "research_id": research_id,
            "source_id": source_id,
            "document_id": document_id,
            "excerpt": excerpt,
            "fingerprint": fingerprint,
            "metadata": metadata,
        }
        return self.client.table("evidences").upsert(row, on_conflict="research_id,fingerprint").execute().data[0]["id"]

    async def save_result(self, research_id: str, section_key: str, question_key: str, question: str, status: ResultStatus, answer: str, summary: str, evidence_ids: list[str]) -> None:
        result = self.client.table("research_results").upsert(
            {
                "research_id": research_id,
                "section_key": section_key,
                "question_key": question_key,
                "question": question,
                "status": status.value,
                "answer": answer,
                "summary": summary,
                "updated_at": utcnow_iso(),
            },
            on_conflict="research_id,question_key",
        ).execute().data[0]
        self.client.table("result_evidences").delete().eq("result_id", result["id"]).execute()
        if evidence_ids:
            self.client.table("result_evidences").insert([{"result_id": result["id"], "evidence_id": evidence_id} for evidence_id in dict.fromkeys(evidence_ids)]).execute()

    async def increment_usage(self, research_id: str, **increments: int) -> None:
        rows = self.client.table("researches").select("usage").eq("id", research_id).limit(1).execute().data
        usage = rows[0].get("usage") or {}
        for key, amount in increments.items():
            usage[key] = int(usage.get(key, 0)) + int(amount)
        self.client.table("researches").update({"usage": usage, "updated_at": utcnow_iso()}).eq("id", research_id).execute()

    async def _summary(self, row: dict[str, Any]) -> ResearchSummary:
        progress_rows = self.client.table("research_progress").select("*").eq("research_id", row["id"]).execute().data
        return ResearchSummary(
            id=row["id"],
            company_id=row["company_id"],
            company=row["company_snapshot"],
            status=ResearchStatus(row["status"]),
            checklist_version=row["checklist_version"],
            progress=[
                ProgressStep(
                    key=item["step_key"],
                    title=item["title"],
                    status=StepStatus(item["status"]),
                    completed_items=item["completed_items"],
                    total_items=item["total_items"],
                    message=item.get("message"),
                )
                for item in progress_rows
            ],
            usage=ResearchUsage(**(row.get("usage") or {})),
            error_public=row.get("error_public"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
            completed_at=row.get("completed_at"),
        )

    async def _detail(self, row: dict[str, Any]) -> ResearchDetail:
        summary = await self._summary(row)
        source_rows = self.client.table("sources").select("*").eq("research_id", row["id"]).execute().data
        sources = {
            item["id"]: SourceRecord(
                id=item["id"],
                research_id=item["research_id"],
                url=item["url"],
                normalized_url=item["normalized_url"],
                title=item.get("title"),
                domain=item.get("domain"),
                source_type=SourceType(item.get("source_type") or SourceType.OTHER),
                description=item.get("description"),
                accessed_at=item.get("accessed_at"),
                metadata=item.get("metadata") or {},
            )
            for item in source_rows
        }
        evidence_rows = self.client.table("evidences").select("*").eq("research_id", row["id"]).execute().data
        evidences = {
            item["id"]: EvidenceRecord(
                id=item["id"],
                research_id=item["research_id"],
                source_id=item["source_id"],
                document_id=item.get("document_id"),
                excerpt=item["excerpt"],
                metadata=item.get("metadata") or {},
                source=sources.get(item["source_id"]),
            )
            for item in evidence_rows
        }
        result_rows = self.client.table("research_results").select("*").eq("research_id", row["id"]).execute().data
        links = self.client.table("result_evidences").select("*").in_("result_id", [item["id"] for item in result_rows] or ["00000000-0000-0000-0000-000000000000"]).execute().data
        evidence_by_result: dict[str, list[EvidenceRecord]] = {}
        for link in links:
            if link["evidence_id"] in evidences:
                evidence_by_result.setdefault(link["result_id"], []).append(evidences[link["evidence_id"]])
        sections: dict[str, dict[str, Any]] = {}
        for result in result_rows:
            section = sections.setdefault(result["section_key"], {"key": result["section_key"], "title": SECTION_TITLES.get(result["section_key"], result["section_key"]), "results": []})
            section["results"].append({**result, "evidences": [item.model_dump(mode="json") for item in evidence_by_result.get(result["id"], [])]})
        return ResearchDetail(**summary.model_dump(), sections=list(sections.values()), sources=list(sources.values()))
