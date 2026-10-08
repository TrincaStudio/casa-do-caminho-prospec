import httpx

from app.core.config import settings
from app.core.retry import retry_async


async def search(query: str, count: int = 8) -> list[dict]:
    if settings.research_mode == "live" and not settings.brave_search_api_key:
        raise RuntimeError("BRAVE_SEARCH_API_KEY is required in live mode")
    if not settings.brave_search_api_key:
        return []

    async def call() -> list[dict]:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            response = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers={"X-Subscription-Token": settings.brave_search_api_key, "Accept": "application/json"},
                params={"q": query, "count": count, "country": "BR", "search_lang": "pt-br", "safesearch": "moderate"},
            )
            response.raise_for_status()
            payload = response.json()
            return [
                {"title": item.get("title"), "url": item.get("url"), "description": item.get("description", "")}
                for item in payload.get("web", {}).get("results", [])
                if item.get("url")
            ]

    return await retry_async(call, settings.external_retry_attempts)
