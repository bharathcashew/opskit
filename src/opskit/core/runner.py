"""Runs selected checks concurrently and collects a RunReport."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from opskit.core.config import Config
from opskit.core.context import Context
from opskit.core.models import CheckResult, Finding, RunReport, Status
from opskit.core.registry import CheckSpec, get_check, list_checks, load_plugins


def select_checks(
    config: Config, check_ids: list[str] | None = None, tags: list[str] | None = None
) -> list[CheckSpec]:
    if check_ids:
        return [get_check(cid) for cid in check_ids]  # explicit ids run even if disabled
    return [s for s in list_checks(tags) if config.check_config(s.id).enabled]


def run_one(spec: CheckSpec, ctx: Context) -> CheckResult:
    params = ctx.config.check_config(spec.id).params
    start = time.perf_counter()
    try:
        findings = spec.func(ctx, **params) or []
        if not all(isinstance(f, Finding) for f in findings):
            raise TypeError("check must return a list of Finding objects")
        status = Status.worst([f.status for f in findings])
        error = None
    except Exception as exc:
        findings, status, error = [], Status.ERROR, f"{type(exc).__name__}: {exc}"
    return CheckResult(
        check_id=spec.id,
        title=spec.title,
        status=status,
        findings=findings,
        duration_ms=int((time.perf_counter() - start) * 1000),
        error=error,
    )


def run_checks(
    config: Config,
    check_ids: list[str] | None = None,
    tags: list[str] | None = None,
) -> RunReport:
    load_plugins(config.plugins)
    specs = select_checks(config, check_ids, tags)
    ctx = Context(config)
    report = RunReport()
    with ThreadPoolExecutor(max_workers=max(1, config.max_workers)) as pool:
        report.results = list(pool.map(lambda s: run_one(s, ctx), specs))
    report.finished_at = datetime.now(timezone.utc)
    report.status = Status.worst([r.status for r in report.results])
    return report
