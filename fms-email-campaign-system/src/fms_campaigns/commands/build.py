"""Build: clone-from-template + render content JSON + PUT to Omnisend.

Reads `series_plan.json` from the content dir for feature/filler picks.
v1 implements the cheap path: if the plan file doesn't exist, generate one
from the matched pool with simple defaults (so `match → build` works without
explicit `plan` step). The proper interactive `plan` command is a follow-up.
"""
from __future__ import annotations

import json
import random
from datetime import datetime
from pathlib import Path

from loguru import logger
from rich.console import Console
from sqlmodel import Session, select

from ..content import build_content
from ..db import Campaign, CollectionMatch, Image, Series, init_db
from ..models import Banner
from ..services import Services

console = Console()


def _load_or_seed_plan(
    plan_path: Path, banners: list[Banner], days: int, portrait_height: int
) -> dict:
    """Return a series plan dict { 'days': [{'feature': Banner, 'fillers': [Banner]*18}] }.

    If `plan_path` exists, load it. Otherwise generate a naive plan and warn.
    """
    if plan_path.exists():
        return json.loads(plan_path.read_text())

    portraits = [b for b in banners if b.height == portrait_height]
    landscapes = [b for b in banners if b.height != portrait_height]

    if len(portraits) < days:
        raise click_compat_error(
            f"Need at least {days} portrait banners for the featured slot, "
            f"only {len(portraits)} available. Add more banners or run interactive plan."
        )
    needed_total = days * 19
    if len(banners) < needed_total:
        raise click_compat_error(
            f"Need at least {needed_total} unique banners; only {len(banners)} matched."
        )

    rng = random.Random(42)  # Deterministic for repeatability
    rng.shuffle(portraits)
    features = portraits[:days]
    used_ids = {b.source_id for b in features}
    pool = [b for b in landscapes + portraits[days:] if b.source_id not in used_ids]
    rng.shuffle(pool)

    plan_days = []
    for i, feat in enumerate(features):
        fillers = pool[i * 18 : (i + 1) * 18]
        if len(fillers) < 18:
            raise click_compat_error(
                f"Day {i+1}: only {len(fillers)} fillers available (need 18)."
            )
        plan_days.append(
            {
                "day": i + 1,
                "feature": feat.model_dump(),
                "fillers": [b.model_dump() for b in fillers],
                "subject": f"🐘 {feat.title} Fabric Collection!",
            }
        )

    plan = {"days": plan_days}
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(plan, indent=2))
    console.print(
        f"[yellow]No plan file found. Wrote a default plan to {plan_path}. "
        f"Edit features/subjects there before re-running.[/yellow]"
    )
    return plan


def click_compat_error(msg: str) -> RuntimeError:
    return RuntimeError(msg)


def _matched_banners(session: Session, brand_id: str) -> list[Banner]:
    rows = session.exec(
        select(Image, CollectionMatch)
        .where(Image.brand_id == brand_id)
        .where(CollectionMatch.image_id == Image.id)
    ).all()
    out: list[Banner] = []
    for img, match in rows:
        out.append(
            Banner(
                source_id=img.id,
                handle=match.handle,
                title=match.title,
                height=img.height,
            )
        )
    return out


def run(services: Services, *, series: str, only_day: int | None, dry_run: bool) -> None:
    config = services.config
    engine = init_db(config.paths.state_db)

    series_dir = config.paths.content_root / series
    series_dir.mkdir(parents=True, exist_ok=True)
    plan_path = series_dir / "series_plan.json"

    with Session(engine) as session:
        if not session.exec(select(Series).where(Series.id == series)).first():
            raise RuntimeError(
                f"No series '{series}' in DB. Run `fms-campaigns ingest --series {series} ...` first."
            )

        banners = _matched_banners(session, config.id)
        if not banners:
            raise RuntimeError("No matched banners. Run match first.")

        # Heuristic: 7 days unless plan says otherwise. Plan file overrides.
        days_to_build = 7
        plan = _load_or_seed_plan(
            plan_path, banners, days_to_build, config.banner_sizes.portrait_height
        )

        for day_entry in plan["days"]:
            day = day_entry["day"]
            if only_day is not None and day != only_day:
                continue

            feature = Banner(**day_entry["feature"])
            fillers = [Banner(**f) for f in day_entry["fillers"]]
            subject = day_entry.get("subject", f"Day {day}")

            campaign = session.exec(
                select(Campaign)
                .where(Campaign.series_id == series)
                .where(Campaign.day_number == day)
            ).first()

            if campaign is None and not dry_run:
                template_id = config.template.campaign_id
                if not template_id:
                    raise RuntimeError(
                        "brand.template.campaign_id is empty. Set it to a known-good "
                        "template campaign id in config/<brand>.toml before building."
                    )
                resp = services.omnisend.copy_campaign(template_id)
                cid = resp.get("id") or resp.get("campaignID")
                content_id = resp.get("contentID") or resp.get("content_id") or ""
                if not cid:
                    raise RuntimeError(f"Unexpected copy response: {resp}")
                name = f"{config.display_name} — {series} — Day {day}: {feature.title}"
                campaign = Campaign(
                    id=cid,
                    series_id=series,
                    day_number=day,
                    name=name,
                    subject=subject,
                    content_id=content_id,
                    feature_handle=feature.handle,
                    status="draft",
                )
                session.add(campaign)
                session.commit()

                services.omnisend.patch_campaign(
                    cid,
                    {
                        "name": name,
                        "content": {
                            "email": {
                                "subject": subject,
                                "preheader": config.preheader,
                                "senderEmail": config.sender_email,
                                "senderName": config.sender_name,
                            }
                        },
                    },
                )

            content_id = campaign.content_id if campaign else f"DRY-day{day}"
            doc = build_content(
                email_content_id=content_id,
                feature=feature,
                fillers=fillers,
                brand=config,
            )
            out_path = series_dir / f"day{day:02d}_{_slug(feature.handle)}.json"
            out_path.write_text(json.dumps(doc, indent=2))
            console.print(f"[green]Wrote[/green] {out_path}")

            if dry_run:
                continue

            assert campaign is not None
            services.omnisend.put_email_content(campaign.content_id, doc)
            campaign.updated_at = datetime.utcnow()
            session.add(campaign)
            session.commit()
            console.print(f"[green]PUT email content for day {day}[/green]")


def _slug(handle: str) -> str:
    return handle.replace("/", "-")
