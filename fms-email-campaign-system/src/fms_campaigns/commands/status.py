"""Status: print every campaign in a series and what state it's in."""
from __future__ import annotations

from rich.console import Console
from rich.table import Table
from sqlmodel import Session, select

from ..config import BrandConfig
from ..db import AuditRun, Campaign, Series, init_db

console = Console()


def run(config: BrandConfig, series: str) -> None:
    engine = init_db(config.paths.state_db)
    with Session(engine) as session:
        s = session.exec(select(Series).where(Series.id == series)).first()
        if not s:
            console.print(f"[yellow]No series '{series}' in DB.[/yellow]")
            return

        campaigns = session.exec(
            select(Campaign).where(Campaign.series_id == series).order_by(Campaign.day_number)
        ).all()

        table = Table(title=f"Series '{series}' (status: {s.status})")
        table.add_column("Day")
        table.add_column("Subject")
        table.add_column("Feature")
        table.add_column("Status")
        table.add_column("Scheduled (UTC)")
        table.add_column("Last audit")

        for c in campaigns:
            last_audit = session.exec(
                select(AuditRun)
                .where(AuditRun.campaign_id == c.id)
                .order_by(AuditRun.run_at.desc())
                .limit(1)
            ).first()
            audit_label = (
                f"{'PASS' if last_audit.passed else 'FAIL'} @ {last_audit.run_at:%Y-%m-%d %H:%M}"
                if last_audit else "—"
            )
            table.add_row(
                str(c.day_number),
                c.subject,
                c.feature_handle or "—",
                c.status,
                str(c.scheduled_at) if c.scheduled_at else "—",
                audit_label,
            )

        console.print(table)
