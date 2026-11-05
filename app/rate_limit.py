"""Simple in-process sliding-window rate limit (casual search abuse control)."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException

_lock = threading.Lock()
_hits: dict[str, deque[float]] = defaultdict(deque)


def enforce_rate_limit(key: str, *, limit: int, window_sec: int) -> None:
    """Raise 429 when `key` exceeds `limit` hits inside `window_sec`."""
    if limit <= 0 or window_sec <= 0:
        return
    now = time.monotonic()
    cutoff = now - window_sec
    with _lock:
        bucket = _hits[key]
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            raise HTTPException(
                status_code=429,
                detail="Too many searches. Please wait a minute and try again.",
            )
        bucket.append(now)
