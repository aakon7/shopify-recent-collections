"""Brand + runtime configuration loader.

Loads `config/<brand>.toml` and overlays environment variables from `.env`.
Secrets are never read from TOML — only from env.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from dotenv import load_dotenv


@dataclass(frozen=True)
class BrandTemplate:
    campaign_id: str
    logo_image_id: str
    mystery_image_id: str
    mystery_product_url: str
    menu_handles: list[str]
    menu_labels: list[str]


@dataclass(frozen=True)
class BannerSizes:
    landscape_height: int
    portrait_height: int
    display_width: int
    source_width: int

    def resize_height(self, source_height: int) -> float:
        return round(self.display_width * source_height / self.source_width, 6)


@dataclass(frozen=True)
class BlockIds:
    images: list[str]
    mystery: str


@dataclass(frozen=True)
class RateLimits:
    shopify_qps: float
    omnisend_qps: float
    shopify_max_retries: int
    shopify_backoff_seconds: float


@dataclass(frozen=True)
class Paths:
    state_db: Path
    content_root: Path
    banner_input_root: Path
    report_root: Path
    log_file: Path


@dataclass(frozen=True)
class Secrets:
    omnisend_api_key: str
    anthropic_api_key: str | None
    shopify_admin_token: str | None


@dataclass(frozen=True)
class BrandConfig:
    id: str
    display_name: str
    sender_email: str
    sender_name: str
    preheader: str
    shopify_domain: str
    shopify_store_handle: str
    timezone: str
    template: BrandTemplate
    banner_sizes: BannerSizes
    block_ids: BlockIds
    rate_limits: RateLimits
    paths: Paths
    secrets: Secrets

    @property
    def shopify_base_url(self) -> str:
        return f"https://{self.shopify_domain}"


def _resolve_path(project_root: Path, value: str) -> Path:
    p = Path(value)
    if not p.is_absolute():
        p = project_root / p
    return p


def load_config(brand: str | None = None, project_root: Path | None = None) -> BrandConfig:
    project_root = project_root or Path.cwd()
    load_dotenv(project_root / ".env", override=False)

    brand = brand or os.environ.get("FMS_BRAND", "fms")
    config_path = project_root / "config" / f"{brand}.toml"
    if not config_path.exists():
        raise FileNotFoundError(f"Brand config not found: {config_path}")

    with config_path.open("rb") as f:
        raw = tomllib.load(f)

    b = raw["brand"]
    template = BrandTemplate(
        campaign_id=b["template"].get("campaign_id", ""),
        logo_image_id=b["template"]["logo_image_id"],
        mystery_image_id=b["template"]["mystery_image_id"],
        mystery_product_url=b["template"]["mystery_product_url"],
        menu_handles=list(b["template"]["menu_handles"]),
        menu_labels=list(b["template"]["menu_labels"]),
    )
    sizes = BannerSizes(
        landscape_height=b["banner_sizes"]["landscape_height"],
        portrait_height=b["banner_sizes"]["portrait_height"],
        display_width=b["banner_sizes"]["display_width"],
        source_width=b["banner_sizes"]["source_width"],
    )
    block_ids = BlockIds(
        images=list(b["block_ids"]["images"]),
        mystery=b["block_ids"]["mystery"],
    )
    rl = raw["rate_limits"]
    rate_limits = RateLimits(
        shopify_qps=rl["shopify_qps"],
        omnisend_qps=rl["omnisend_qps"],
        shopify_max_retries=rl["shopify_max_retries"],
        shopify_backoff_seconds=rl["shopify_backoff_seconds"],
    )
    pp = raw["paths"]
    state_dir_override = os.environ.get("FMS_STATE_DIR")
    state_db = (
        _resolve_path(project_root, f"{state_dir_override}/state.db")
        if state_dir_override
        else _resolve_path(project_root, pp["state_db"])
    )
    paths = Paths(
        state_db=state_db,
        content_root=_resolve_path(project_root, pp["content_root"]),
        banner_input_root=_resolve_path(project_root, pp["banner_input_root"]),
        report_root=_resolve_path(project_root, pp["report_root"]),
        log_file=_resolve_path(project_root, pp["log_file"]),
    )
    secrets = Secrets(
        omnisend_api_key=os.environ.get("OMNISEND_API_KEY", ""),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
        shopify_admin_token=os.environ.get("SHOPIFY_ADMIN_TOKEN") or None,
    )

    if len(block_ids.images) != 19:
        raise ValueError(
            f"brand.block_ids.images must have 19 entries, got {len(block_ids.images)}"
        )

    return BrandConfig(
        id=b["id"],
        display_name=b["display_name"],
        sender_email=b["sender_email"],
        sender_name=b["sender_name"],
        preheader=b["preheader"],
        shopify_domain=b["shopify_domain"],
        shopify_store_handle=b["shopify_store_handle"],
        timezone=b["timezone"],
        template=template,
        banner_sizes=sizes,
        block_ids=block_ids,
        rate_limits=rate_limits,
        paths=paths,
        secrets=secrets,
    )
