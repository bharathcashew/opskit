"""Output formats for a RunReport."""

from __future__ import annotations

from rich.console import Console
from rich.markup import escape
from rich.table import Table

from opskit.core.models import RunReport, Status

_COLORS = {
    Status.OK: "green",
    Status.WARN: "yellow",
    Status.CRITICAL: "bold red",
    Status.ERROR: "magenta",
    Status.SKIPPED: "dim",
}


def to_json(report: RunReport) -> str:
    return report.model_dump_json(indent=2)


def to_markdown(report: RunReport) -> str:
    lines = [
        f"# opskit run `{report.run_id}`: **{report.status.value.upper()}**",
        "",
        "| Check | Status | Findings | Time |",
        "|---|---|---|---|",
    ]
    for r in report.results:
        lines.append(
            f"| {r.title} (`{r.check_id}`) | {r.status.value} | {len(r.findings)} | {r.duration_ms} ms |"
        )
    for r in report.results:
        if not r.findings and not r.error:
            continue
        lines += ["", f"## {r.title}"]
        if r.error:
            lines.append(f"- error: `{r.error}`")
        for f in r.findings:
            where = f" [{f.region}]" if f.region else ""
            lines.append(f"- **{f.status.value}** `{f.resource}`{where}: {f.message}")
    return "\n".join(lines) + "\n"


def print_table(report: RunReport, console: Console | None = None, verbose: bool = True) -> None:
    console = console or Console()
    t = Table(title=f"opskit run {report.run_id}", show_lines=False)
    t.add_column("Check")
    t.add_column("Status")
    t.add_column("Findings", justify="right")
    t.add_column("Time", justify="right")
    for r in report.results:
        c = _COLORS[r.status]
        t.add_row(r.check_id, f"[{c}]{r.status.value}[/{c}]", str(len(r.findings)), f"{r.duration_ms} ms")
    console.print(t)
    if verbose:
        for r in report.results:
            if r.error:
                console.print(f"[magenta]{r.check_id}[/magenta] error: {escape(r.error)}", highlight=False)
            for f in r.findings:
                c = _COLORS[f.status]
                where = f" [{f.region}]" if f.region else ""
                text = escape(f"{f.resource}{where}: {f.message}")
                label = f"[{c}]{f.status.value:8}[/{c}]"
                console.print(f"  {label} {r.check_id}  {text}", highlight=False)
    c = _COLORS[report.status]
    counts = ", ".join(f"{n} {s}" for s, n in report.summary().items() if n)
    console.print(f"\nOverall: [{c}]{report.status.value.upper()}[/{c}]  ({counts})", highlight=False)
