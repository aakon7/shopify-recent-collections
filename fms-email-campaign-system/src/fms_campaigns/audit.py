"""Audit subsystem — the part of the rewrite that earns its keep.

Three classes of check (per spec §7.7):
- Cheap (always on): block counts, required fields, resize math, within-email
  duplicate handles, Mystery Bundle position, footer unsubscribe link.
- Medium (always on): HTTP-200 + non-empty for every unique collection link.
- Deep (--deep flag): banner art vs alt text vision check. (Stubbed in v1; the
  module exposes the entry point but skips by default.)

The cheap checks are *structural* — they look at the local content JSON only.
The medium checks call out to the live storefront via the rate-limited
HttpClient. Deep checks would call Anthropic's vision API.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import BrandConfig
from .models import (
    AuditReport,
    LinkCheckResult,
    ResizeMismatch,
    WithinEmailDuplicate,
)
from .shopify import ShopifyClient


_COLLECTION_RE = re.compile(r"/collections/([a-z0-9-]+)/?$")


def _collection_handle_from_link(link: str) -> str | None:
    m = _COLLECTION_RE.search(link.split("?")[0])
    return m.group(1) if m else None


def cheap_checks(content: dict[str, Any], day: int, brand: BrandConfig) -> tuple[
    list[str], list[ResizeMismatch], list[WithinEmailDuplicate], list[str]
]:
    """Return (structural_errors, resize_mismatches, within_email_dupes, block_count_errors)."""
    structural: list[str] = []
    resize_mismatches: list[ResizeMismatch] = []
    block_count_errors: list[str] = []
    dupes_out: list[WithinEmailDuplicate] = []

    sections = content.get("sections", [])
    if len(sections) != 3:
        structural.append(f"Day {day}: expected 3 sections, got {len(sections)}")
        return structural, resize_mismatches, dupes_out, block_count_errors

    try:
        blocks = sections[1]["rows"][0]["columns"][0]["blocks"]
    except (KeyError, IndexError) as e:
        structural.append(f"Day {day}: cannot reach section 1 blocks: {e}")
        return structural, resize_mismatches, dupes_out, block_count_errors

    image_blocks = [b for b in blocks if b.get("type") == "image"]
    menu_blocks = [b for b in blocks if b.get("type") == "menu"]

    if len(image_blocks) != 20:
        block_count_errors.append(
            f"Day {day}: expected 20 image blocks (19 banners + Mystery), got {len(image_blocks)}"
        )
    if len(menu_blocks) != 1:
        block_count_errors.append(f"Day {day}: expected 1 menu block, got {len(menu_blocks)}")

    sizes = brand.banner_sizes
    handles_by_position: dict[int, str] = {}
    for pos, b in enumerate(image_blocks):
        img = b.get("image", {})
        for required in ("altText", "id", "link", "height", "resizeHeight", "source", "width"):
            if required not in img:
                structural.append(
                    f"Day {day} pos {pos}: missing required field {required}"
                )

        h = img.get("height")
        rh = img.get("resizeHeight")
        if isinstance(h, int) and isinstance(rh, (int, float)):
            expected = sizes.resize_height(h)
            if abs(rh - expected) > 0.5:
                resize_mismatches.append(
                    ResizeMismatch(
                        day=day,
                        position=pos,
                        alt_text=img.get("altText", ""),
                        actual=float(rh),
                        expected=expected,
                    )
                )

        link = img.get("link", "")
        handle = _collection_handle_from_link(link)
        if handle:
            handles_by_position[pos] = handle

    # Mystery Bundle is the last image block
    if image_blocks:
        last = image_blocks[-1].get("image", {})
        if last.get("link") != brand.template.mystery_product_url:
            structural.append(
                f"Day {day}: last image block link is {last.get('link')!r}, "
                f"expected Mystery Bundle ({brand.template.mystery_product_url})"
            )
        if last.get("id") != brand.template.mystery_image_id:
            structural.append(
                f"Day {day}: last image block id is {last.get('id')!r}, "
                f"expected Mystery image id"
            )

    # Within-email handle duplication
    handle_to_positions: dict[str, list[int]] = defaultdict(list)
    for pos, handle in handles_by_position.items():
        handle_to_positions[handle].append(pos)
    for handle, positions in handle_to_positions.items():
        if len(positions) > 1:
            dupes_out.append(
                WithinEmailDuplicate(day=day, handle=handle, positions=sorted(positions))
            )

    # Footer must contain [[unsubscribe_link]] — Omnisend rejects without it
    footer_section = sections[2]
    footer_blocks = footer_section.get("rows", [{}])[0].get("columns", [{}])[0].get("blocks", [])
    has_unsub = any(
        "[[unsubscribe_link]]" in (b.get("text") or "")
        for b in footer_blocks
        if b.get("type") == "text"
    )
    if not has_unsub:
        structural.append(f"Day {day}: footer missing [[unsubscribe_link]] (Omnisend will reject)")

    # Cross-day: block ids unique within an email (template reuses are OK across emails)
    all_block_ids = [b.get("id") for b in blocks]
    bid_counts = Counter(all_block_ids)
    dupe_bids = [bid for bid, n in bid_counts.items() if n > 1]
    if dupe_bids:
        structural.append(f"Day {day}: duplicate block ids within email: {dupe_bids}")

    return structural, resize_mismatches, dupes_out, block_count_errors


def medium_checks(
    handles_to_check: set[str],
    shopify: ShopifyClient,
    *,
    require_products: bool = True,
) -> tuple[list[LinkCheckResult], list[LinkCheckResult]]:
    """HTTP-validate every unique collection handle. Returns (failed, empty).

    `failed` = anything that's not HTTP 200.
    `empty` = HTTP 200 but products_count == 0 (only populated if require_products=True).
    """
    failed: list[LinkCheckResult] = []
    empty: list[LinkCheckResult] = []

    for handle in sorted(handles_to_check):
        url = f"{shopify.base_url}/collections/{handle}"
        exists, status = shopify.collection_exists(handle)
        if not exists:
            failed.append(
                LinkCheckResult(url=url, status=status, is_ok=False, note="collection 404")
            )
            continue
        if require_products:
            count = shopify.collection_products_count(handle)
            if count == 0:
                empty.append(
                    LinkCheckResult(
                        url=url,
                        status=200,
                        products_count=0,
                        is_ok=False,
                        note="collection exists but has zero products",
                    )
                )

    return failed, empty


def audit_series(
    series_name: str,
    content_dir: Path,
    brand: BrandConfig,
    shopify: ShopifyClient | None,
    *,
    days: list[int] | None = None,
    require_products: bool = True,
    deep: bool = False,
) -> AuditReport:
    """Audit every day{N}_*.json in content_dir. Returns a report."""
    if not content_dir.exists():
        raise FileNotFoundError(f"Content dir not found: {content_dir}")

    files = sorted(content_dir.glob("day*.json"))
    if days is not None:
        files = [f for f in files if _extract_day(f.name) in days]

    report = AuditReport(
        series=series_name,
        days_checked=[_extract_day(f.name) for f in files],
        total_links=0,
    )

    handles_to_check: set[str] = set()
    # Always include the menu links + Mystery Bundle for completeness
    for handle in brand.template.menu_handles:
        handles_to_check.add(handle)

    for path in files:
        day = _extract_day(path.name)
        try:
            content = json.loads(path.read_text())
        except json.JSONDecodeError as e:
            report.structural_errors.append(f"Day {day}: invalid JSON in {path.name}: {e}")
            continue

        structural, resize_mismatches, dupes, block_count_errors = cheap_checks(
            content, day, brand
        )
        report.structural_errors.extend(structural)
        report.resize_mismatches.extend(resize_mismatches)
        report.within_email_dupes.extend(dupes)
        report.block_count_errors.extend(block_count_errors)

        # Collect handles for medium check
        for section in content.get("sections", []):
            for row in section.get("rows", []):
                for col in row.get("columns", []):
                    for b in col.get("blocks", []):
                        if b.get("type") == "image":
                            handle = _collection_handle_from_link(b.get("image", {}).get("link", ""))
                            if handle:
                                handles_to_check.add(handle)

    report.total_links = len(handles_to_check)

    if shopify is not None:
        failed, empty = medium_checks(
            handles_to_check, shopify, require_products=require_products
        )
        report.failed_links.extend(failed)
        report.empty_collections.extend(empty)

    if deep:
        # v1: stub. Wire up Anthropic vision check here in a follow-up.
        report.art_mismatches.append(
            {"note": "deep audit not implemented in v1; --deep flag is a no-op"}
        )

    return report


def render_markdown_report(report: AuditReport) -> str:
    """Pretty-print an AuditReport as Markdown for ./reports/<series>/audit_*.md."""
    lines = [
        f"# Audit report — {report.series}",
        "",
        f"_Run at {datetime.utcnow().isoformat()}Z_",
        f"_Days checked: {', '.join(str(d) for d in report.days_checked) or 'none'}_",
        f"_Total unique links: {report.total_links}_",
        "",
        f"**Result: {'PASSED ✓' if report.passed else 'FAILED ✗'}**",
        "",
    ]

    def _section(title: str, items: list[Any]) -> None:
        if not items:
            return
        lines.append(f"## {title} ({len(items)})")
        lines.append("")
        for item in items:
            if hasattr(item, "model_dump"):
                lines.append(f"- `{json.dumps(item.model_dump(), default=str)}`")
            else:
                lines.append(f"- {item}")
        lines.append("")

    _section("Structural errors", report.structural_errors)
    _section("Block count errors", report.block_count_errors)
    _section("Resize mismatches", report.resize_mismatches)
    _section("Within-email duplicate handles", report.within_email_dupes)
    _section("Failed link checks (404 / network)", report.failed_links)
    _section("Empty collections (200 but zero products)", report.empty_collections)
    if report.art_mismatches:
        _section("Banner art / alt text mismatches", report.art_mismatches)

    return "\n".join(lines)


def _extract_day(filename: str) -> int:
    m = re.match(r"day0*(\d+)", filename)
    return int(m.group(1)) if m else 0
