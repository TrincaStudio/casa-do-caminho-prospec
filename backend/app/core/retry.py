import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

import httpx


T = TypeVar("T")


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    attempts: int,
    base_delay: float = 0.5,
    retry_statuses: set[int] | None = None,
) -> T:
    retry_statuses = retry_statuses or {408, 409, 425, 429, 500, 502, 503, 504}
    last_error: Exception | None = None
    for attempt in range(max(1, attempts)):
        try:
            return await fn()
        except httpx.HTTPStatusError as exc:
            last_error = exc
            if exc.response.status_code not in retry_statuses or attempt == attempts - 1:
                raise
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            last_error = exc
            if attempt == attempts - 1:
                raise
        await asyncio.sleep(base_delay * (2**attempt))
    assert last_error is not None
    raise last_error
