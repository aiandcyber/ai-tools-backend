"""In-flight tool job cancel registry (best-effort cooperative cancel)."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field


@dataclass
class Job:
    id: str
    tool_id: str
    cancel: threading.Event = field(default_factory=threading.Event)


_JOBS: dict[str, Job] = {}
_LOCK = threading.Lock()


def create_job(tool_id: str, job_id: str | None = None) -> Job:
    job = Job(id=(job_id or uuid.uuid4().hex), tool_id=tool_id)
    with _LOCK:
        _JOBS[job.id] = job
    return job


def get_job(job_id: str) -> Job | None:
    with _LOCK:
        return _JOBS.get(job_id)


def cancel_job(job_id: str) -> bool:
    job = get_job(job_id)
    if not job:
        return False
    job.cancel.set()
    return True


def finish_job(job_id: str) -> None:
    with _LOCK:
        _JOBS.pop(job_id, None)


def is_cancelled(job_id: str | None) -> bool:
    if not job_id:
        return False
    job = get_job(job_id)
    return bool(job and job.cancel.is_set())
