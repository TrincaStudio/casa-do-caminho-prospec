import pytest

from app.core.checklist import SECTIONS
from app.core.enums import ResearchStatus, ResultStatus
from app.core.urltools import domain_from_url, normalize_url
from app.research.orchestrator import _evidence_excerpt
from app.research.planner import SearchGroup, classify_source, create_research_plan, select_relevant_sources


def test_checklist_has_expected_shape():
    assert len(SECTIONS) == 6
    assert sum(len(section["questions"]) for section in SECTIONS) == 65


def test_status_enums_are_internal_english():
    assert ResultStatus.FOUND.value == "FOUND"
    assert ResearchStatus.COMPLETED_WITH_WARNINGS.value == "COMPLETED_WITH_WARNINGS"


def test_url_normalization_removes_tracking():
    normalized = normalize_url("https://www.Example.com/path/?utm_source=x&ok=1#section")
    assert normalized == "https://example.com/path?ok=1"
    assert domain_from_url(normalized) == "example.com"


def test_planner_groups_questions_and_reduces_searches():
    plan = create_research_plan({"name": "Empresa Teste", "cnpj": "00.000.000/0001-00", "website": "https://empresa.test"})
    assert len(plan.questions) == 65
    assert len(plan.searches) < 65
    assert plan.groups[SearchGroup.COMPATIBILITY]


def test_planner_keeps_search_queries_broad_enough_for_web_search():
    plan = create_research_plan({"name": "Trinca Studio"})

    assert plan.searches[0].is_general is True
    assert plan.searches[0].query == '"Trinca Studio"'
    assert '"Trinca Studio" empresa cadastro' in [item.query for item in plan.searches]
    assert all(len(item.query.split()) <= 5 for item in plan.searches if not item.query.startswith("site:"))


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://www.gov.br/cgu/pt-br", "OFFICIAL_GOVERNMENT"),
        ("https://www.cvm.gov.br/noticias", "REGULATORY"),
        ("https://empresa.com/sustentabilidade", "OFFICIAL_COMPANY"),
        ("https://g1.globo.com/economia", "JOURNALISTIC"),
    ],
)
def test_source_classification(url, expected):
    assert classify_source(url, "https://empresa.com").value == expected


def test_select_relevant_sources_deduplicates_urls():
    hits = [
        {"url": "https://example.com/a?utm_source=x", "title": "A"},
        {"url": "https://example.com/a?utm_source=y", "title": "A duplicate"},
        {"url": "https://example.com/b", "title": "B"},
    ]
    selected = select_relevant_sources(hits, {"name": "Empresa"}, limit=10)
    assert len(selected) == 2


def test_evidence_excerpt_removes_markdown_markup():
    excerpt = _evidence_excerpt(
        "![logo](https://example.com/logo.png) [Conheca a VOLL](https://example.com) **Texto publico**",
        "fallback",
    )

    assert excerpt == "logo Conheca a VOLL Texto publico"
