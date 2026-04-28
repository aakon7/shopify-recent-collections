"""Schedule: PATCH each day's campaign with sendingSettings, then POST send.

Hard-gates on the most recent audit having passed (override with --force).
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta

from rich.console import Console
from rich.table import Table
from sqlmodel import Session, select

from ..db import AuditRun, Campaign, init_db
from ..schedule import local_to_utc_iso
from ..services import Services

console = Console()


def _last_audit(session: Session, campaign_id: str) -> AuditRun | None:
    return session.exec(
        select(AuditRun)
        .where(AuditRun.campaign_id == campaign_id)
        .order_by(AuditRun.run_at.desc())
        .limit(1)
    ).first()


def run(
    services: Services,
    *,
    series: str,
    start: str,
    time_str: str,
    force: bool,
) -> None:
    config = services.config
    engine = init_db(config.paths.state_db)

    table = Table(title=f"Schedule — {series}")
    table.add_column("Day")
    table.add_column("Campaign")
    table.add_column("Local")
    table.add_column("UTC")
    table.add_column("Audit")
    table.add_column("Action")

    with Session(engine) as session:
        campaigns = session.exec(
            select(Campaign).where(Campaign.series_id == series).order_by(Campaign.day_number)
        ).all()
        if not campaigns:
            raise RuntimeError(f"No campaigns for series '{series}'. Run build first.")

        any_blocked = False
        for c in campaigns:
            local_date_str = (
                datetime.strptime(start, "%Y-%m-%d") + timedelta(days=c.day_number - 1)
            ).strftime("%Y-%m-%d")
            utc_iso = local_to_utc_iso(local_date_str, time_str, config.timezone)

            audit = _last_audit(session, c.id)
            audit_label = (
                "passed" if audit and audit.passed else "FAILED" if audit else "no audit"
            )

            allowed = (audit is not None and audit.passed) or force
            action = "scheduled" if allowed else "BLOCKED"

            if not allowed:
                any_blocked = True
                table.add_row(
                    str(c.day_number), c.id, f"{local_date_str} {time_str}", utc_iso,
                    audit_label, "[red]BLOCKED[/red]",
                )
                continue

            services.omnisend.patch_campaign(
                c.id,
                {
                    "sendingSettings": {
                        "strategy": "scheduled",
                        "scheduledAt": utc_iso,
                        "isTZOptimizationEnabled": False,
                    }
                },
            )
            services.omnisend.send_campaign(c.id)
            c.scheduled_at = datetime.fromisoformat(utc_iso.replace("Z", "+00:00"))
            c.status = "scheduled"
            c.updated_at = datetime.utcnow()
            session.add(c)
            session.commit()

            table.add_row(
                str(c.day_number), c.id, f"{local_date_str} {time_str}", utc_iso,
                audit_label, "[green]scheduled[/green]" if allowed else action,
            )

    console.print(table)
    if any_blocked and not force:
        console.print(
            "[red]Some days blocked because audit didn't pass. Re-audit or pass --force.[/red]"
        )
        sys.exit(2)
