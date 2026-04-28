"""SQLite state. Tables roughly mirror §5 of the build spec.

We use SQLModel (pydantic + SQLAlchemy) so model classes double as ORM rows
and pydantic validation. Schema lives here; migrations are handled by simply
calling `init_db` at startup — for a single-operator tool there's no Alembic
machinery. If the schema evolves, bump SCHEMA_VERSION and add a `_migrate_*`
function.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlmodel import Column, Field, SQLModel, create_engine
from sqlalchemy import JSON

SCHEMA_VERSION = 1


class Brand(SQLModel, table=True):
    id: str = Field(primary_key=True)
    display_name: str
    sender_email: str
    sender_name: str
    preheader: str
    shopify_domain: str
    timezone: str = "America/Chicago"


class Image(SQLModel, table=True):
    id: str = Field(primary_key=True)
    brand_id: str = Field(foreign_key="brand.id", index=True)
    filename: str
    sha256: str = Field(index=True)
    width: int
    height: int
    image_format: str
    source_path: str
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)


class CollectionMatch(SQLModel, table=True):
    image_id: str = Field(primary_key=True, foreign_key="image.id")
    brand_id: str = Field(foreign_key="brand.id", index=True)
    handle: str = Field(index=True)
    title: str
    products_count_min: int = 0
    exists: bool = True
    last_verified_at: datetime | None = None
    match_method: str = "ocr"  # ocr, manual, fuzzy, filename
    confidence: float = 0.0


class CachedCollection(SQLModel, table=True):
    """Cache of live Shopify collection handles (refreshed on demand)."""

    handle: str = Field(primary_key=True)
    brand_id: str = Field(primary_key=True, foreign_key="brand.id")
    title: str
    last_seen_at: datetime = Field(default_factory=datetime.utcnow)


class Series(SQLModel, table=True):
    id: str = Field(primary_key=True)
    brand_id: str = Field(foreign_key="brand.id", index=True)
    name: str = Field(index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "planning"  # planning, building, scheduled, sent, archived


class Campaign(SQLModel, table=True):
    id: str = Field(primary_key=True)  # Omnisend campaign id
    series_id: str = Field(foreign_key="series.id", index=True)
    day_number: int
    name: str
    subject: str
    content_id: str
    status: str = "draft"
    scheduled_at: datetime | None = None
    feature_handle: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class BannerBlock(SQLModel, table=True):
    """One row per (campaign, position). Position 0 is the featured slot."""

    campaign_id: str = Field(primary_key=True, foreign_key="campaign.id")
    position: int = Field(primary_key=True)
    block_id: str
    image_id: str = Field(foreign_key="image.id")
    alt_text: str
    link_url: str
    height: int
    resize_height: float
    hash_at_last_audit: str | None = None


class AuditRun(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    campaign_id: str = Field(foreign_key="campaign.id", index=True)
    run_at: datetime = Field(default_factory=datetime.utcnow)
    links_checked: int = 0
    links_404: int = 0
    empty_collections: int = 0
    art_mismatches: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    within_email_dupes: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    passed: bool = False
    notes: str = ""


class EditLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    campaign_id: str = Field(foreign_key="campaign.id", index=True)
    edit_kind: str
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SchemaMeta(SQLModel, table=True):
    """Single-row table tracking schema version for future migrations."""

    id: int = Field(default=1, primary_key=True)
    version: int = SCHEMA_VERSION
    initialized_at: datetime = Field(default_factory=datetime.utcnow)


def init_db(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine
