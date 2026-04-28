"""Audit: run cheap + medium checks across a series, write a Markdown report,
record an audit_run row in SQLite. Exits non-zero on failure (so cron can alert).
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from rich.console import Console
from sqlmodel import Session, select

from ..audit import audit_series, render_markdown_report
from ..db import AuditRun, Campaign, Series, init_db
from ..services import Services

console = Console()


def run(
    services: Services,
    *,
    series: str,
    deep: bool = False,
    no_network: bool = False,
) -> None:
    config = services.config
    engine = init_db(config.paths.state_db)

    series_dir = config.paths.content_root / series
    if not series_dir.exists():
        raise RuntimeError(
            f"Series content dir not found: {series_dir}. Run build first."
        )

    report = audit_series(
        series_name=series,
        content_dir=series_dir,
        brand=config,
        shopify=None if no_network else services.shopify,
        deep=deep,
    )

    md = render_markdown_report(report)
    report_dir = config.paths.report_root / series
    report_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    out_path = report_dir / f"audit_{ts}.md"
    out_path.write_text(md)

    console.print(md)
    console.print(f"\n[bold]Report:[/bold] {out_path}")

    with Session(engine) as session:
        if session.exec(select(Series).where(Series.id == series)).first():
            for day in report.days_checked:
                campaign = session.exec(
                    select(Campaign)
                    .where(Campaign.series_id == series)
                    .where(Campaign.day_number == day)
                ).first()
                if campaign is None:
                    continue
                day_failed = [
                    fl for fl in report.failed_links
                    if any(d.day == day for d in report.within_email_dupes if d.handle in fl.url)
                ]
                run_row = AuditRun(
                    campaign_id=campaign.id,
                    links_checked=report.total_links,
                    links_404=len(report.failed_links),
                    empty_collections=len(report.empty_collections),
                    art_mismatches=report.art_mismatches,
                    within_email_dupes=[d.model_dump() for d in report.within_email_dupes if d.day == day],
                    passed=report.passed,
                    notes=f"day-level slice from series-wide audit; failed_in_series={len(day_failed)}",
                )
                session.add(run_row)
            session.commit()

    if not report.passed:
        console.print("[red]Audit FAILED.[/red] Fix issues and re-run before scheduling.")
        sys.exit(1)
    console.print("[green]Audit PASSED.[/green]")
