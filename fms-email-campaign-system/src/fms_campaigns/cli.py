"""CLI entry point. `fms-campaigns ...` from the shell maps to commands here.

Each command is a thin wrapper that:
1. Loads brand config + builds the service bundle.
2. Calls into a pure module function (commands/<name>.py).
3. Renders results with rich.

Per the spec §15: hard gate audit-before-schedule with --force escape hatch.
"""
from __future__ import annotations

import sys
from pathlib import Path

import click
from loguru import logger
from rich.console import Console

from . import __version__
from .config import load_config
from .services import build_services

console = Console()


def _setup_logging(log_file: Path, verbose: bool) -> None:
    logger.remove()
    level = "DEBUG" if verbose else "INFO"
    logger.add(sys.stderr, level=level, format="<level>{level: <8}</level> | {message}")
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_file,
        rotation="5 MB",
        retention=10,
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}",
    )


@click.group()
@click.option("--brand", default=None, help="Brand id (matches config/<brand>.toml)")
@click.option("-v", "--verbose", is_flag=True, help="Enable DEBUG logging on stderr")
@click.version_option(__version__, prog_name="fms-campaigns")
@click.pass_context
def cli(ctx: click.Context, brand: str | None, verbose: bool) -> None:
    """FMS banner email campaign pipeline."""
    config = load_config(brand=brand)
    _setup_logging(config.paths.log_file, verbose)
    ctx.ensure_object(dict)
    ctx.obj["config"] = config


@cli.command("status")
@click.option("--series", required=True, help="Series name")
@click.pass_context
def status_cmd(ctx: click.Context, series: str) -> None:
    """Show what state each day is in for a series."""
    from .commands import status as cmd

    cmd.run(ctx.obj["config"], series)


@cli.command("ingest")
@click.option("--series", required=True)
@click.option("--folder", required=True, type=click.Path(exists=True, file_okay=False))
@click.option("--dry-run", is_flag=True, help="Catalog files but skip Omnisend upload")
@click.pass_context
def ingest_cmd(ctx: click.Context, series: str, folder: str, dry_run: bool) -> None:
    """Register banner files and upload them to Omnisend's image library."""
    from .commands import ingest as cmd

    services = build_services(ctx.obj["config"])
    try:
        cmd.run(services, series=series, folder=Path(folder), dry_run=dry_run)
    finally:
        services.close()


@cli.command("match")
@click.option("--series", required=True)
@click.option("--auto/--no-auto", default=True, help="Auto-confirm above-threshold matches")
@click.option("--threshold", type=float, default=0.3, show_default=True)
@click.pass_context
def match_cmd(ctx: click.Context, series: str, auto: bool, threshold: float) -> None:
    """OCR each banner and propose a Shopify collection handle."""
    from .commands import match as cmd

    services = build_services(ctx.obj["config"])
    try:
        cmd.run(services, series=series, auto=auto, threshold=threshold)
    finally:
        services.close()


@cli.command("build")
@click.option("--series", required=True)
@click.option("--day", type=int, default=None, help="Build only this day (default: all days)")
@click.option("--dry-run", is_flag=True, help="Write content JSON locally; skip Omnisend PUT")
@click.pass_context
def build_cmd(ctx: click.Context, series: str, day: int | None, dry_run: bool) -> None:
    """Render day{N}_content.json and PUT to Omnisend."""
    from .commands import build as cmd

    services = build_services(ctx.obj["config"])
    try:
        cmd.run(services, series=series, only_day=day, dry_run=dry_run)
    finally:
        services.close()


@cli.command("audit")
@click.option("--series", required=True)
@click.option(
    "--deep",
    is_flag=True,
    help="(Stub in v1) Run vision LLM banner-art check on suspect banners",
)
@click.option("--no-network", is_flag=True, help="Skip medium HTTP checks (cheap-only)")
@click.pass_context
def audit_cmd(ctx: click.Context, series: str, deep: bool, no_network: bool) -> None:
    """Verify a series before scheduling."""
    from .commands import audit as cmd

    services = build_services(ctx.obj["config"])
    try:
        cmd.run(services, series=series, deep=deep, no_network=no_network)
    finally:
        services.close()


@cli.command("schedule")
@click.option("--series", required=True)
@click.option("--start", required=True, help="YYYY-MM-DD (local date for day 1)")
@click.option("--time", "time_str", default="09:00", show_default=True, help="HH:MM local time")
@click.option(
    "--force",
    is_flag=True,
    help="Schedule even if the most recent audit didn't pass (NOT recommended)",
)
@click.pass_context
def schedule_cmd(
    ctx: click.Context, series: str, start: str, time_str: str, force: bool
) -> None:
    """Set the send time for every campaign in a series."""
    from .commands import schedule as cmd

    services = build_services(ctx.obj["config"])
    try:
        cmd.run(services, series=series, start=start, time_str=time_str, force=force)
    finally:
        services.close()


@cli.command("brand")
@click.argument("action", type=click.Choice(["show", "refresh-collections"]))
@click.pass_context
def brand_cmd(ctx: click.Context, action: str) -> None:
    """Brand config commands."""
    from .commands import brand as cmd

    services = build_services(ctx.obj["config"])
    try:
        cmd.run(services, action=action)
    finally:
        services.close()


def main() -> None:  # entry point for testing
    cli()  # pylint: disable=no-value-for-parameter


if __name__ == "__main__":
    main()
