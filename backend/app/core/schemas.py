from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, HttpUrl, field_validator

from app.core.enums import ResearchStatus, ResultStatus, SourceType, StepStatus


class CompanyInput(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    cnpj: str | None = Field(default=None, max_length=32)
    website: str | None = Field(default=None, max_length=300)
    idempotency_key: str | None = Field(default=None, max_length=120)

    @field_validator("name", "cnpj", "website", "idempotency_key")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value


class UserContext(BaseModel):
    id: str
    email: str | None = None
    access_token: str | None = None


class SourceRecord(BaseModel):
    id: str
    research_id: str
    url: str
    normalized_url: str
    title: str | None = None
    domain: str | None = None
    source_type: SourceType = SourceType.OTHER
    description: str | None = None
    accessed_at: datetime | None = None
    published_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceRecord(BaseModel):
    id: str
    research_id: str
    source_id: str
    document_id: str | None = None
    excerpt: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    source: SourceRecord | None = None


class ResultRecord(BaseModel):
    id: str | None = None
    research_id: str
    section_key: str
    question_key: str
    question: str
    status: ResultStatus
    answer: str
    summary: str
    evidence_ids: list[str] = Field(default_factory=list)
    evidences: list[EvidenceRecord] = Field(default_factory=list)


class ProgressStep(BaseModel):
    key: str
    title: str
    status: StepStatus
    completed_items: int = 0
    total_items: int = 0
    message: str | None = None


class ResearchUsage(BaseModel):
    brave_searches: int = 0
    urls_selected: int = 0
    firecrawl_calls: int = 0
    openai_calls: int = 0
    openai_input_tokens: int = 0
    openai_output_tokens: int = 0
    duration_ms: int = 0
    warnings: int = 0


class ResearchSummary(BaseModel):
    id: str
    company_id: str | None = None
    company: dict[str, Any]
    status: ResearchStatus
    checklist_version: str
    progress: list[ProgressStep] = Field(default_factory=list)
    usage: ResearchUsage = Field(default_factory=ResearchUsage)
    error_public: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None


class ResearchDetail(ResearchSummary):
    sections: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[SourceRecord] = Field(default_factory=list)


class CancelResearchOut(BaseModel):
    id: str
    status: ResearchStatus
