"""Command-line interface: `opskit list`, `opskit run`, `opskit serve`, `opskit init`."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from opskit import __version__
from opskit.core.config import SAMPLE_CONFIG, load_config
from opskit.core.registry import list_checks, load_plugins
from opskit.core.runner import run_checks
from opskit.reporters import print_table, to_json, to_markdown

app = typer.Typer(help="opskit: pluggable IT ops checks from the CLI or a REST API.", no_args_is_help=True)
console = Console()


class Format(str, Enum):
    table = "table"
    json = "json"
    markdown = "markdown"


ConfigOpt = typer.Option(None, "--config", "-c", help="Path to opskit.yaml")


@app.command("version")
def version() -> None:
    """Print the version."""
    console.print(__version__)


@app.command("init")
def init(path: Path = typer.Argument(Path("opskit.yaml")), force: bool = False) -> None:
    """Write a sample config file."""
    if path.exists() and not force:
        console.print(f"[yellow]{path} already exists (use --force to overwrite)[/yellow]")
        raise typer.Exit(1)
    path.write_text(SAMPLE_CONFIG)
    console.print(f"wrote {path}")


@app.command("list")
def list_cmd(
    tag: list[str] | None = typer.Option(None, "--tag", "-t", help="Filter by tag (repeatable)"),
    config: Path | None = ConfigOpt,
) -> None:
    """List available checks."""
    cfg = load_config(config)
    load_plugins(cfg.plugins)
    t = Table()
    t.add_column("ID", no_wrap=True)
    for col in ("Title", "Tags", "Params", "Enabled"):
        t.add_column(col)
    for s in list_checks(tag):
        enabled = "yes" if cfg.check_config(s.id).enabled else "no"
        params = ", ".join(f"{k}={v}" for k, v in s.params.items())
        t.add_row(s.id, s.title, ",".join(s.tags), params, enabled)
    console.print(t)


@app.command("run")
def run(
    checks: list[str] | None = typer.Argument(None, help="Check ids to run (default: all enabled)"),
    tag: list[str] | None = typer.Option(None, "--tag", "-t", help="Only checks with this tag"),
    region: list[str] | None = typer.Option(None, "--region", "-r", help="Override AWS regions"),
    profile: str | None = typer.Option(None, "--profile", "-p", help="Override AWS profile"),
    fmt: Format = typer.Option(Format.table, "--format", "-f"),
    output: Path | None = typer.Option(None, "--output", "-o", help="Write report to file"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Table only, no finding details"),
    config: Path | None = ConfigOpt,
) -> None:
    """Run checks. Exit code: 0 ok, 1 warnings, 2 critical or errors."""
    cfg = load_config(config)
    if region:
        cfg.aws.regions = region
    if profile:
        cfg.aws.profile = profile
    try:
        report = run_checks(cfg, check_ids=checks, tags=tag)
    except KeyError as exc:
        console.print(f"[red]{exc.args[0]}[/red]")
        raise typer.Exit(2) from None

    if fmt == Format.table and not output:
        print_table(report, console, verbose=not quiet)
    else:
        text = to_json(report) if fmt == Format.json else to_markdown(report)
        if fmt == Format.table:  # table requested with --output: save markdown
            text = to_markdown(report)
        if output:
            output.write_text(text)
            console.print(f"wrote {output}")
        else:
            typer.echo(text)
    raise typer.Exit(report.exit_code)


@app.command("serve")
def serve(
    host: str | None = typer.Option(None, help="Bind address"),
    port: int | None = typer.Option(None, help="Port"),
    config: Path | None = ConfigOpt,
) -> None:
    """Start the REST API."""
    import uvicorn

    from opskit.api.app import create_app

    cfg = load_config(config)
    if not cfg.api.token:
        console.print(
            "[yellow]OPSKIT_API_TOKEN is not set: the API will accept "
            "unauthenticated requests.[/yellow]"
        )
    uvicorn.run(create_app(cfg), host=host or cfg.api.host, port=port or cfg.api.port)


if __name__ == "__main__":
    app()
