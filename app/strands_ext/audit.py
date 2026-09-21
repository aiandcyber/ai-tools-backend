"""Shared in-memory audit trail for Strands hooks (interview / demo visibility)."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from threading import Lock
from typing import Any

_LOCK = Lock()
_EVENTS: deque[dict[str, Any]] = deque(maxlen=80)


def record(kind: str, **payload: Any) -> None:
    item = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        **payload,
    }
    with _LOCK:
        _EVENTS.appendleft(item)


def recent(limit: int = 25) -> list[dict[str, Any]]:
    with _LOCK:
        return list(_EVENTS)[: max(1, min(limit, 80))]


def clear() -> None:
    with _LOCK:
        _EVENTS.clear()
