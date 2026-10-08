from dataclasses import dataclass, field

from app.core.checklist import SECTIONS
from app.core.enums import SearchGroup, SourceType
from app.core.urltools import domain_from_url, normalize_url


CHECKLIST_VERSION = "2026-10-mvp"


SECTION_TO_GROUP = {
    "identificacao": SearchGroup.IDENTIFICATION,
    "valores": SearchGroup.INSTITUTIONAL,
    "responsabilidade_social": SearchGroup.SOCIAL_RESPONSIBILITY,
    "esg": SearchGroup.ESG,
    "integridade": SearchGroup.INTEGRITY,
    "compatibilidade": SearchGroup.COMPATIBILITY,
}


GROUP_TITLES = {
    SearchGroup.IDENTIFICATION: "Identificacao",
    SearchGroup.INSTITUTIONAL: "Institucional",
    SearchGroup.SOCIAL_RESPONSIBILITY: "Responsabilidade Social",
    SearchGroup.ESG: "ESG",
    SearchGroup.INTEGRITY: "Integridade",
    SearchGroup.COMPATIBILITY: "Compatibilidade Casa do Caminho",
}


@dataclass(frozen=True)
class PlannedQuestion:
    section_key: str
    question_key: str
    question: str
    group: SearchGroup


@dataclass(frozen=True)
class SearchPlanItem:
    group: SearchGroup
    query: str
    purpose: str


@dataclass
class ResearchPlan:
    checklist_version: str
    questions: list[PlannedQuestion]
    searches: list[SearchPlanItem]
    groups: dict[SearchGroup, list[PlannedQuestion]] = field(default_factory=dict)


def checklist_questions() -> list[PlannedQuestion]:
    questions: list[PlannedQuestion] = []
    for section in SECTIONS:
        group = SECTION_TO_GROUP[section["key"]]
        for key, question in section["questions"]:
            questions.append(
                PlannedQuestion(
                    section_key=section["key"],
                    question_key=key,
                    question=question,
                    group=group,
                )
            )
    return questions


def create_research_plan(company: dict) -> ResearchPlan:
    name = company["name"].strip()
    cnpj = (company.get("cnpj") or "").strip()
    website = (company.get("website") or "").strip()
    official_domain = domain_from_url(website) if website else ""
    identity = " ".join(part for part in [f'"{name}"', cnpj] if part)

    searches = [
        SearchPlanItem(SearchGroup.IDENTIFICATION, f"{identity} razao social cnpj sede setor site oficial", "Dados cadastrais e perfil"),
        SearchPlanItem(SearchGroup.IDENTIFICATION, f"{identity} produtos servicos porte tempo de mercado", "Perfil comercial"),
        SearchPlanItem(SearchGroup.INSTITUTIONAL, f"{identity} missao valores codigo de etica compliance direitos humanos diversidade inclusao", "Valores e politicas"),
        SearchPlanItem(SearchGroup.SOCIAL_RESPONSIBILITY, f"{identity} responsabilidade social investimento social privado instituto fundacao voluntariado doacoes saude oncologia", "Responsabilidade social"),
        SearchPlanItem(SearchGroup.SOCIAL_RESPONSIBILITY, f"{identity} leis de incentivo campanhas sociais OSCs apoiadas parcerias sociais", "Projetos sociais e parcerias"),
        SearchPlanItem(SearchGroup.ESG, f"{identity} ESG sustentabilidade relatorio anual ambiental governanca", "ESG e sustentabilidade"),
        SearchPlanItem(SearchGroup.INTEGRITY, f"{identity} sancoes multas investigacao corrupcao fraude lavagem de dinheiro", "Integridade e sancoes"),
        SearchPlanItem(SearchGroup.INTEGRITY, f"{identity} processo judicial trabalhista ambiental TAC ministerio publico recuperacao judicial falencia noticias negativas", "Reputacao e controversias"),
    ]
    if official_domain:
        searches.extend(
            [
                SearchPlanItem(SearchGroup.INSTITUTIONAL, f"site:{official_domain} missao valores compliance sustentabilidade", "Site oficial institucional"),
                SearchPlanItem(SearchGroup.SOCIAL_RESPONSIBILITY, f"site:{official_domain} social voluntariado doacoes instituto fundacao", "Site oficial social"),
                SearchPlanItem(SearchGroup.ESG, f"site:{official_domain} ESG sustentabilidade relatorio", "Site oficial ESG"),
            ]
        )

    questions = checklist_questions()
    groups: dict[SearchGroup, list[PlannedQuestion]] = {group: [] for group in SearchGroup}
    for question in questions:
        groups[question.group].append(question)
    return ResearchPlan(CHECKLIST_VERSION, questions, searches, groups)


GOV_DOMAINS = ("gov.br", ".gov.br", "jus.br", "mp.br", "leg.br")
REGULATORY_DOMAINS = ("cvm.gov.br", "bcb.gov.br", "anvisa.gov.br", "ibama.gov.br", "gov.br/cgu")
JOURNALISTIC_HINTS = ("g1.globo.com", "folha.uol.com.br", "estadao.com.br", "valor.globo.com", "uol.com.br", "cnnbrasil.com.br")


def classify_source(url: str, company_website: str | None = None) -> SourceType:
    normalized = normalize_url(url)
    domain = domain_from_url(normalized)
    official_domain = domain_from_url(company_website) if company_website else ""
    if official_domain and domain == official_domain:
        return SourceType.OFFICIAL_COMPANY
    if any(domain.endswith(item) for item in REGULATORY_DOMAINS):
        return SourceType.REGULATORY
    if any(domain.endswith(item) for item in GOV_DOMAINS):
        return SourceType.OFFICIAL_GOVERNMENT
    if any(domain.endswith(item) for item in JOURNALISTIC_HINTS):
        return SourceType.JOURNALISTIC
    if any(word in normalized for word in ("relatorio", "sustentabilidade", "institucional", "compliance")):
        return SourceType.INSTITUTIONAL
    return SourceType.OTHER


SOURCE_PRIORITY = {
    SourceType.OFFICIAL_GOVERNMENT: 0,
    SourceType.REGULATORY: 1,
    SourceType.OFFICIAL_COMPANY: 2,
    SourceType.INSTITUTIONAL: 3,
    SourceType.JOURNALISTIC: 4,
    SourceType.OTHER: 5,
}


def select_relevant_sources(hits: list[dict], company: dict, limit: int) -> list[dict]:
    seen: set[str] = set()
    selected: list[dict] = []
    for hit in hits:
        url = hit.get("url")
        if not url:
            continue
        normalized = normalize_url(url)
        if normalized in seen:
            continue
        seen.add(normalized)
        source_type = classify_source(normalized, company.get("website"))
        selected.append({**hit, "normalized_url": normalized, "source_type": source_type})
    selected.sort(key=lambda item: (SOURCE_PRIORITY[item["source_type"]], item.get("title") or ""))
    return selected[:limit]
