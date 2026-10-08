import json
from typing import Any

from openai import OpenAI

from app.core.config import settings
from app.core.enums import ResultStatus


SYSTEM = """Voce e um analista de pesquisa para uma organizacao social.
Responda apenas com base nas evidencias fornecidas. A ausencia de evidencia nao prova inexistencia.
Nao atribua score, nao aprove, nao reprove e nao recomende decisao. Em temas juridicos ou reputacionais,
descreva fatos e fontes sem concluir culpa, ilegalidade ou condenacao. Retorne somente JSON no schema pedido.
Use apenas evidence_ids existentes. Nunca invente URLs, fontes ou evidencias."""


def _fallback_answers(questions: list[dict[str, Any]], reason: str) -> dict[str, Any]:
    return {
        "answers": [
            {
                "question_id": question["question_key"],
                "status": ResultStatus.INCONCLUSIVE.value,
                "answer": "Nao foi possivel concluir com as evidencias disponiveis.",
                "summary": reason,
                "evidence_ids": [],
            }
            for question in questions
        ],
        "usage": {"input_tokens": 0, "output_tokens": 0},
    }


def analyze_questions(company: dict, questions: list[dict[str, Any]], evidences: list[dict[str, Any]]) -> dict[str, Any]:
    if settings.research_mode == "live" and not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required in live mode")
    if not settings.openai_api_key:
        return _fallback_answers(questions, "Integracao de IA indisponivel no ambiente atual.")

    client = OpenAI(api_key=settings.openai_api_key, timeout=settings.request_timeout_seconds)
    prompt = json.dumps(
        {
            "empresa": company,
            "perguntas": questions,
            "evidencias": evidences,
            "instrucoes": [
                "Cada pergunta deve receber uma resposta.",
                "Use NOT_FOUND somente quando a busca foi executada e nao ha evidencia publica suficiente.",
                "Use INCONCLUSIVE quando as evidencias forem ambiguas ou insuficientes.",
                "Use REQUIRES_HUMAN_REVIEW para temas reputacionais/juridicos sensiveis ou conflito de fontes.",
            ],
        },
        ensure_ascii=False,
    )
    schema = {
        "type": "object",
        "properties": {
            "answers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "question_id": {"type": "string"},
                        "status": {"type": "string", "enum": [status.value for status in ResultStatus]},
                        "answer": {"type": "string"},
                        "summary": {"type": "string"},
                        "evidence_ids": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["question_id", "status", "answer", "summary", "evidence_ids"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["answers"],
        "additionalProperties": False,
    }
    response = client.responses.create(
        model=settings.openai_model,
        input=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
        text={"format": {"type": "json_schema", "name": "research_answers", "strict": True, "schema": schema}},
    )
    parsed = json.loads(response.output_text)
    usage = getattr(response, "usage", None)
    parsed["usage"] = {
        "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
    }
    return parsed
