from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from time import monotonic
from typing import Any

from app.connectors.brave import search as brave_search
from app.connectors.firecrawl import scrape
from app.core.config import settings
from app.core.enums import ResearchStatus, ResultStatus, SearchGroup, SourceType, StepStatus
from app.core.urltools import domain_from_url, normalize_url
from app.repositories.base import Repository
from app.research.planner import GROUP_TITLES, create_research_plan, select_relevant_sources
from app.services.ai import analyze_questions


def _hash(value: str) -> str:
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()


def _content_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _mock_document(source: dict[str, Any], company: dict[str, Any]) -> dict[str, Any]:
    text = (
        f"Documento de demonstracao para {company['name']}. "
        f"Fonte: {source.get('title') or source.get('url')}. "
        "Contem informacoes publicas simuladas para validar o fluxo de pesquisa, evidencias e dossie."
    )
    return {"markdown": text, "metadata": {"mock": True}}


def _mock_search(query: str, company: dict[str, Any]) -> list[dict[str, Any]]:
    site = company.get("website") or "https://example.org"
    return [
        {"title": f"{company['name']} - site institucional", "url": site, "description": "Fonte oficial informada pelo usuario."},
        {"title": f"{company['name']} responsabilidade social", "url": f"{site.rstrip('/')}/responsabilidade-social", "description": "Pagina institucional simulada."},
        {"title": f"{company['name']} sustentabilidade", "url": f"{site.rstrip('/')}/sustentabilidade", "description": "Relatorio ESG simulado."},
    ]


def _evidence_excerpt(content: str, fallback: str) -> str:
    compact = " ".join(content.split())
    if not compact:
        compact = fallback
    return compact[:900]


class ResearchOrchestrator:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    async def run(self, research_id: str) -> None:
        started = monotonic()
        detail = await self.repository.get_research(research_id)
        if not detail:
            return
        if detail.status == ResearchStatus.CANCELLED:
            return

        warnings = 0
        company = detail.company
        plan = create_research_plan(company)

        for group, questions in plan.groups.items():
            if questions:
                await self.repository.upsert_progress_step(research_id, group.value, GROUP_TITLES[group], StepStatus.WAITING, 0, len(questions))

        try:
            all_hits: list[dict[str, Any]] = []
            searches = plan.searches[: settings.max_brave_queries_per_research]
            for index, item in enumerate(searches, start=1):
                await self.repository.upsert_progress_step(research_id, item.group.value, GROUP_TITLES[item.group], StepStatus.PROCESSING, 0, len(plan.groups[item.group]), f"Busca {index}/{len(searches)}")
                query_hash = _hash(item.query)
                expires_after = datetime.now(timezone.utc) - timedelta(hours=settings.search_cache_ttl_hours)
                cached = await self.repository.get_cached_search(query_hash, expires_after)
                if cached is not None:
                    hits = cached
                else:
                    try:
                        hits = _mock_search(item.query, company) if settings.research_mode == "mock" else await brave_search(item.query, count=8)
                        await self.repository.increment_usage(research_id, brave_searches=0 if cached is not None else 1)
                        await self.repository.save_search_execution(research_id, item.group.value, item.query, query_hash, hits, "COMPLETED")
                    except Exception as exc:
                        warnings += 1
                        await self.repository.increment_usage(research_id, warnings=1)
                        await self.repository.save_search_execution(research_id, item.group.value, item.query, query_hash, [], "FAILED", str(exc))
                        continue
                for hit in hits:
                    all_hits.append({**hit, "group": item.group.value})

            selected_sources = select_relevant_sources(all_hits, company, settings.max_urls_per_research)
            await self.repository.increment_usage(research_id, urls_selected=len(selected_sources))

            evidence_by_group: dict[SearchGroup, list[dict[str, Any]]] = {group: [] for group in SearchGroup}
            processed_pages = 0
            for source in selected_sources:
                if processed_pages >= settings.max_firecrawl_pages_per_research:
                    break
                normalized_url = source["normalized_url"]
                source_id = await self.repository.upsert_source(
                    research_id,
                    {
                        "url": source["url"],
                        "normalized_url": normalized_url,
                        "title": source.get("title"),
                        "domain": domain_from_url(normalized_url),
                        "source_type": source.get("source_type", SourceType.OTHER),
                        "description": source.get("description"),
                        "metadata": {"search_group": source.get("group")},
                    },
                )
                expires_after = datetime.now(timezone.utc) - timedelta(hours=settings.document_cache_ttl_hours)
                document = await self.repository.get_cached_document(normalized_url, expires_after)
                if document:
                    content = document.get("content", "")
                    document_id = document["id"]
                else:
                    try:
                        page = _mock_document(source, company) if settings.research_mode == "mock" else await scrape(source["url"])
                        processed_pages += 1
                        await self.repository.increment_usage(research_id, firecrawl_calls=0 if settings.research_mode == "mock" else 1)
                    except Exception as exc:
                        warnings += 1
                        await self.repository.increment_usage(research_id, warnings=1)
                        continue
                    content = (page or {}).get("markdown", "")[: settings.max_content_chars_per_document]
                    document_id = await self.repository.save_document(
                        research_id,
                        source_id,
                        {
                            "url": source["url"],
                            "normalized_url": normalized_url,
                            "content": content,
                            "content_hash": _content_hash(content),
                            "metadata": (page or {}).get("metadata", {}),
                        },
                    )
                excerpt = _evidence_excerpt(content, source.get("description") or source.get("title") or source["url"])
                evidence_id = await self.repository.save_evidence(
                    research_id,
                    source_id,
                    document_id,
                    excerpt,
                    {"source_type": str(source.get("source_type", SourceType.OTHER)), "search_group": source.get("group")},
                )
                group = SearchGroup(source.get("group") or SearchGroup.IDENTIFICATION.value)
                evidence_by_group[group].append(
                    {
                        "evidence_id": evidence_id,
                        "source_id": source_id,
                        "title": source.get("title"),
                        "url": source["url"],
                        "source_type": str(source.get("source_type", SourceType.OTHER)),
                        "excerpt": excerpt,
                    }
                )

            for group, questions in plan.groups.items():
                if not questions:
                    continue
                await self.repository.upsert_progress_step(research_id, group.value, GROUP_TITLES[group], StepStatus.PROCESSING, 0, len(questions), "Analisando evidencias")
                group_evidences = evidence_by_group.get(group, [])
                if group == SearchGroup.COMPATIBILITY:
                    group_evidences = [item for values in evidence_by_group.values() for item in values]
                question_payload = [
                    {"question_key": question.question_key, "question": question.question, "section_key": question.section_key}
                    for question in questions
                ]
                if settings.research_mode == "mock":
                    ai_payload = self._mock_answers(question_payload, group_evidences)
                else:
                    ai_payload = await asyncio.to_thread(analyze_questions, company, question_payload, group_evidences)
                    await self.repository.increment_usage(
                        research_id,
                        openai_calls=1,
                        openai_input_tokens=ai_payload.get("usage", {}).get("input_tokens", 0),
                        openai_output_tokens=ai_payload.get("usage", {}).get("output_tokens", 0),
                    )
                answers = {answer["question_id"]: answer for answer in ai_payload.get("answers", [])}
                valid_evidence_ids = {item["evidence_id"] for item in group_evidences}
                completed = 0
                for question in questions:
                    answer = answers.get(question.question_key)
                    if not answer:
                        answer = {
                            "status": ResultStatus.INCONCLUSIVE.value,
                            "answer": "Nao foi possivel concluir com as evidencias disponiveis.",
                            "summary": "A analise nao retornou resposta estruturada para esta pergunta.",
                            "evidence_ids": [],
                        }
                    evidence_ids = [eid for eid in answer.get("evidence_ids", []) if eid in valid_evidence_ids]
                    await self.repository.save_result(
                        research_id,
                        question.section_key,
                        question.question_key,
                        question.question,
                        ResultStatus(answer["status"]),
                        answer["answer"],
                        answer["summary"],
                        evidence_ids,
                    )
                    completed += 1
                    await self.repository.upsert_progress_step(research_id, group.value, GROUP_TITLES[group], StepStatus.PROCESSING, completed, len(questions))
                await self.repository.upsert_progress_step(research_id, group.value, GROUP_TITLES[group], StepStatus.COMPLETED, len(questions), len(questions))

            duration_ms = int((monotonic() - started) * 1000)
            await self.repository.increment_usage(research_id, duration_ms=duration_ms)
            final_status = ResearchStatus.COMPLETED_WITH_WARNINGS if warnings else ResearchStatus.COMPLETED
            await self.repository.update_research_status(research_id, final_status)
        except Exception as exc:
            await self.repository.update_research_status(
                research_id,
                ResearchStatus.FAILED,
                error_public="Nao foi possivel concluir a pesquisa. Consulte os logs tecnicos do backend.",
                error_internal=repr(exc),
            )

    def _mock_answers(self, questions: list[dict[str, Any]], evidences: list[dict[str, Any]]) -> dict[str, Any]:
        evidence_ids = [item["evidence_id"] for item in evidences[:2]]
        answers: list[dict[str, Any]] = []
        for index, question in enumerate(questions):
            status = [ResultStatus.FOUND, ResultStatus.FOUND, ResultStatus.NOT_FOUND, ResultStatus.INCONCLUSIVE][index % 4]
            answers.append(
                {
                    "question_id": question["question_key"],
                    "status": status.value,
                    "answer": "Resposta de demonstracao gerada pelo modo mock.",
                    "summary": f"Resultado mock para: {question['question']}",
                    "evidence_ids": evidence_ids if status == ResultStatus.FOUND else [],
                }
            )
        return {"answers": answers, "usage": {"input_tokens": 0, "output_tokens": 0}}
