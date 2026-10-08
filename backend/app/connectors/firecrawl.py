import httpx

from app.core.config import settings
from app.core.retry import retry_async


async def scrape(url: str) -> dict | None:
    if settings.research_mode == "live" and not settings.firecrawl_api_key:
        raise RuntimeError("FIRECRAWL_API_KEY is required in live mode")
    if not settings.firecrawl_api_key:
        return None

    async def call() -> dict | None:
        async with httpx.AsyncClient(timeout=settings.firecrawl_timeout_seconds) as client:
            response = await client.post(
                "https://api.firecrawl.dev/v1/scrape",
                headers={"Authorization": f"Bearer {settings.firecrawl_api_key}"},
                json={"url": url, "formats": ["markdown"], "onlyMainContent": True},
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json().get("data", {})
            markdown = (data.get("markdown") or "")[: settings.max_content_chars_per_document]
            return {"markdown": markdown, "metadata": data.get("metadata", {})}

    return await retry_async(call, settings.external_retry_attempts)
