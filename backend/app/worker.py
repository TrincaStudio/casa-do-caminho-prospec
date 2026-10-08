import asyncio
import logging
import os
from uuid import uuid4

from app.core.config import settings
from app.core.enums import ResearchStatus
from app.repositories.factory import get_repository
from app.research.orchestrator import ResearchOrchestrator

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("research-worker")


async def run_once(worker_id: str) -> bool:
    repository = get_repository()
    research = await repository.claim_next_pending(worker_id)
    if not research:
        return False
    logger.info("claimed research %s", research.id)
    if research.status == ResearchStatus.CANCELLED:
        return True
    await ResearchOrchestrator(repository).run(research.id)
    return True


async def main() -> None:
    settings.validate_staging_readiness()
    worker_id = f"worker-{uuid4()}"
    logger.info("worker started: %s", worker_id)
    while True:
        did_work = await run_once(worker_id)
        if not did_work:
            await asyncio.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    asyncio.run(main())
