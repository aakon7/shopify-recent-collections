"""Brand: show config, refresh cached collections from Shopify."""
from __future__ import annotations

from datetime import datetime

import httpx
from loguru import logger
from rich.console import Console
from rich.table import Table
from sqlmodel import Session, select

from ..db import Brand as BrandRow
from ..db import CachedCollection, init_db
from ..services import Services

console = Console()


def _show(services: Services) -> None:
    c = services.config
    table = Table(title=f"Brand: {c.id}")
    table.add_column("Key")
    table.add_column("Value")
    rows = [
        ("display_name", c.display_name),
        ("sender_email", c.sender_email),
        ("sender_name", c.sender_name),
        ("preheader", c.preheader),
        ("shopify_domain", c.shopify_domain),
        ("timezone", c.timezone),
        ("template.campaign_id", c.template.campaign_id or "(unset)"),
        ("template.logo_image_id", c.template.logo_image_id),
        ("template.mystery_image_id", c.template.mystery_image_id),
        ("rate_limits.shopify_qps", str(c.rate_limits.shopify_qps)),
        ("rate_limits.omnisend_qps", str(c.rate_limits.omnisend_qps)),
        ("paths.state_db", str(c.paths.state_db)),
        ("paths.content_root", str(c.paths.content_root)),
        ("paths.report_root", str(c.paths.report_root)),
        ("secrets.OMNISEND_API_KEY", "set" if c.secrets.omnisend_api_key else "[red]MISSING[/red]"),
        ("secrets.ANTHROPIC_API_KEY", "set" if c.secrets.anthropic_api_key else "(unset)"),
        ("secrets.SHOPIFY_ADMIN_TOKEN", "set" if c.secrets.shopify_admin_token else "(unset)"),
    ]
    for k, v in rows:
        table.add_row(k, v)
    console.print(table)


def _refresh_collections(services: Services) -> None:
    """Pull every collection from the storefront and cache to SQLite.

    Uses the public storefront `/collections.json?limit=250` paginator.
    """
    config = services.config
    engine = init_db(config.paths.state_db)
    page = 1
    all_handles: dict[str, str] = {}

    while True:
        resp = services.http.get(
            f"{config.shopify_base_url}/collections.json",
            params={"limit": 250, "page": page},
        )
        if resp.status_code != 200:
            logger.error(f"Storefront returned {resp.status_code} on page {page}")
            break
        try:
            data = resp.json()
        except Exception:
            logger.error("Could not parse collections.json")
            break
        cols = data.get("collections", []) if isinstance(data, dict) else []
        if not cols:
            break
        for c in cols:
            handle = c.get("handle")
            title = c.get("title", "")
            if handle:
                all_handles[handle] = title
        if len(cols) < 250:
            break
        page += 1

    console.print(f"Found {len(all_handles)} collections.")

    with Session(engine) as session:
        if not session.exec(select(BrandRow).where(BrandRow.id == config.id)).first():
            session.add(
                BrandRow(
                    id=config.id,
                    display_name=config.display_name,
                    sender_email=config.sender_email,
                    sender_name=config.sender_name,
                    preheader=config.preheader,
                    shopify_domain=config.shopify_domain,
                    timezone=config.timezone,
                )
            )
            session.commit()

        now = datetime.utcnow()
        for handle, title in all_handles.items():
            existing = session.exec(
                select(CachedCollection)
                .where(CachedCollection.brand_id == config.id)
                .where(CachedCollection.handle == handle)
            ).first()
            if existing:
                existing.title = title
                existing.last_seen_at = now
                session.add(existing)
            else:
                session.add(
                    CachedCollection(
                        handle=handle, brand_id=config.id, title=title, last_seen_at=now
                    )
                )
        session.commit()
    console.print("[green]Cached collections refreshed.[/green]")


def run(services: Services, *, action: str) -> None:
    if action == "show":
        _show(services)
    elif action == "refresh-collections":
        _refresh_collections(services)
    else:  # pragma: no cover
        raise ValueError(f"Unknown brand action: {action}")
