"""REST API. Same engine as the CLI, so anything you can run locally you can run as a service.

Endpoints
  GET  /health              liveness probe (no auth)
  GET  /v1/checks           list checks, optional ?tag=
  POST /v1/runs             run checks, returns the report
  GET  /v1/runs             recent runs (summaries)
  GET  /v1/runs/{run_id}    one full report
  GET  /metrics             Prometheus text format for the latest run

Auth: if a token is configured (OPSKIT_API_TOKEN), every /v1 and /metrics call needs
`Authorization: Bearer <token>`.
"""

from __future__ import annotations

import secrets
import threading
from collections import OrderedDict

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from opskit import __version__
from opskit.core.config import Config, load_config
from opskit.core.models import RunReport, Status
from opskit.core.registry import list_checks, load_plugins
from opskit.core.runner import run_checks


class RunRequest(BaseModel):
    checks: list[str] | None = Field(None, description="Check ids; default is all enabled checks")
    tags: list[str] | None = None
    regions: list[str] | None = Field(None, description="Override configured AWS regions")


class RunStore:
    """In-memory, bounded run history. Swap for a database if you need persistence."""

    def __init__(self, size: int):
        self.size = size
        self._runs: OrderedDict[str, RunReport] = OrderedDict()
        self._lock = threading.Lock()

    def add(self, report: RunReport) -> None:
        with self._lock:
            self._runs[report.run_id] = report
            while len(self._runs) > self.size:
                self._runs.popitem(last=False)

    def get(self, run_id: str) -> RunReport | None:
        return self._runs.get(run_id)

    def recent(self, limit: int) -> list[RunReport]:
        with self._lock:
            return list(reversed(self._runs.values()))[:limit]

    def latest(self) -> RunReport | None:
        with self._lock:
            return next(reversed(self._runs.values()), None) if self._runs else None


def create_app(config: Config | None = None) -> FastAPI:
    cfg = config or load_config()
    load_plugins(cfg.plugins)
    store = RunStore(cfg.api.history_size)
    app = FastAPI(title="opskit", version=__version__)
    app.state.config = cfg
    app.state.store = store

    def require_token(request: Request) -> None:
        token = cfg.api.token
        if not token:
            return
        header = request.headers.get("authorization", "")
        scheme, _, supplied = header.partition(" ")
        if scheme.lower() != "bearer" or not secrets.compare_digest(supplied, token):
            raise HTTPException(status_code=401, detail="invalid or missing bearer token")

    auth = [Depends(require_token)]

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    @app.get("/v1/checks", dependencies=auth)
    def get_checks(tag: list[str] | None = Query(None)) -> list[dict]:
        return [
            {**s.to_dict(), "enabled": cfg.check_config(s.id).enabled} for s in list_checks(tag)
        ]

    # Sync handler: FastAPI runs it in a worker thread, so blocking AWS calls are fine.
    @app.post("/v1/runs", dependencies=auth, response_model=RunReport)
    def create_run(req: RunRequest) -> RunReport:
        run_cfg = cfg.model_copy(deep=True)
        if req.regions:
            run_cfg.aws.regions = req.regions
        try:
            report = run_checks(run_cfg, check_ids=req.checks, tags=req.tags)
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=str(exc.args[0])) from None
        store.add(report)
        return report

    @app.get("/v1/runs", dependencies=auth)
    def get_runs(limit: int = Query(20, ge=1, le=500)) -> list[dict]:
        return [
            {
                "run_id": r.run_id,
                "started_at": r.started_at,
                "status": r.status,
                "summary": r.summary(),
            }
            for r in store.recent(limit)
        ]

    @app.get("/v1/runs/{run_id}", dependencies=auth, response_model=RunReport)
    def get_run(run_id: str) -> RunReport:
        report = store.get(run_id)
        if not report:
            raise HTTPException(status_code=404, detail="run not found")
        return report

    @app.get("/metrics", dependencies=auth, response_class=PlainTextResponse)
    def metrics() -> str:
        report = store.latest()
        lines = [
            "# HELP opskit_check_status Latest status per check (0 ok,1 warn,2 error,3 critical,-1 skipped)",
            "# TYPE opskit_check_status gauge",
        ]
        code = {Status.OK: 0, Status.WARN: 1, Status.ERROR: 2, Status.CRITICAL: 3, Status.SKIPPED: -1}
        if report:
            for r in report.results:
                lines.append(f'opskit_check_status{{check="{r.check_id}"}} {code[r.status]}')
            lines += [
                "# HELP opskit_check_findings Findings per check in the latest run",
                "# TYPE opskit_check_findings gauge",
            ]
            for r in report.results:
                lines.append(f'opskit_check_findings{{check="{r.check_id}"}} {len(r.findings)}')
            lines += [
                "# TYPE opskit_last_run_timestamp_seconds gauge",
                f"opskit_last_run_timestamp_seconds {report.started_at.timestamp():.0f}",
            ]
        return "\n".join(lines) + "\n"

    return app
