"""Data models shared by the CLI, the API and every check."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Status(str, Enum):
    OK = "ok"
    WARN = "warn"
    CRITICAL = "critical"
    ERROR = "error"  # the check itself failed to run
    SKIPPED = "skipped"

    @property
    def severity(self) -> int:
        return _SEVERITY[self]

    @classmethod
    def worst(cls, statuses: list[Status]) -> Status:
        if not statuses:
            return cls.OK
        return max(statuses, key=lambda s: s.severity)


_SEVERITY = {
    Status.SKIPPED: 0,
    Status.OK: 1,
    Status.WARN: 2,
    Status.ERROR: 3,
    Status.CRITICAL: 4,
}


class Finding(BaseModel):
    """One observation about one resource."""

    resource: str
    message: str
    status: Status = Status.WARN
    region: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class CheckResult(BaseModel):
    check_id: str
    title: str
    status: Status
    findings: list[Finding] = Field(default_factory=list)
    duration_ms: int = 0
    error: str | None = None


class RunReport(BaseModel):
    run_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    status: Status = Status.OK
    results: list[CheckResult] = Field(default_factory=list)

    @property
    def exit_code(self) -> int:
        """0 = all good, 1 = warnings, 2 = critical or errors. Handy for cron and CI."""
        if self.status in (Status.CRITICAL, Status.ERROR):
            return 2
        if self.status == Status.WARN:
            return 1
        return 0

    def summary(self) -> dict[str, int]:
        counts = {s.value: 0 for s in Status}
        for r in self.results:
            counts[r.status.value] += 1
        return counts
