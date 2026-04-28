"""Audit checks tests — focuses on cheap (structural) checks since medium
checks require a live storefront. Coverage target per spec: > 90%.
"""
from __future__ import annotations

import json
from pathlib import Path

from fms_campaigns.audit import audit_series, cheap_checks, render_markdown_report
from fms_campaigns.content import build_content
from fms_campaigns.models import Banner


def _sample_banners() -> tuple[Banner, list[Banner]]:
    feature = Banner(source_id="a" * 24, handle="butter-waffle", title="Butter Waffle", height=566)
    fillers = [
        Banner(source_id=f"{i:024x}", handle=f"filler-{i}", title=f"Filler {i}", height=378)
        for i in range(18)
    ]
    return feature, fillers


def test_cheap_checks_pass_on_clean_doc(brand_config) -> None:
    feature, fillers = _sample_banners()
    doc = build_content("c", feature, fillers, brand_config)

    structural, resize_mismatches, dupes, block_count_errors = cheap_checks(doc, 1, brand_config)
    assert structural == []
    assert resize_mismatches == []
    assert dupes == []
    assert block_count_errors == []


def test_within_email_duplicate_detected(brand_config) -> None:
    feature, fillers = _sample_banners()
    # Force a duplicate handle into one of the fillers
    fillers[5] = Banner(
        source_id=fillers[5].source_id, handle="butter-waffle", title="Dup", height=378
    )
    doc = build_content("c", feature, fillers, brand_config)
    _, _, dupes, _ = cheap_checks(doc, 3, brand_config)
    assert len(dupes) == 1
    assert dupes[0].handle == "butter-waffle"
    assert 0 in dupes[0].positions  # the feature
    assert 6 in dupes[0].positions  # filler index 5 → image position 6 (0=feature)


def test_resize_mismatch_detected(brand_config) -> None:
    feature, fillers = _sample_banners()
    doc = build_content("c", feature, fillers, brand_config)
    # Corrupt one block's resizeHeight
    blocks = doc["sections"][1]["rows"][0]["columns"][0]["blocks"]
    image_blocks = [b for b in blocks if b["type"] == "image"]
    image_blocks[3]["image"]["resizeHeight"] = 999.0
    _, mismatches, _, _ = cheap_checks(doc, 2, brand_config)
    assert len(mismatches) == 1
    assert mismatches[0].day == 2


def test_missing_unsubscribe_link_flagged(brand_config) -> None:
    feature, fillers = _sample_banners()
    doc = build_content("c", feature, fillers, brand_config)
    # Strip [[unsubscribe_link]] from the footer
    footer_blocks = doc["sections"][2]["rows"][0]["columns"][0]["blocks"]
    for b in footer_blocks:
        if b.get("type") == "text" and "unsubscribe_link" in (b.get("text") or ""):
            b["text"] = b["text"].replace("[[unsubscribe_link]]", "REMOVED")
    structural, _, _, _ = cheap_checks(doc, 4, brand_config)
    assert any("unsubscribe" in s.lower() for s in structural)


def test_mystery_position_check(brand_config) -> None:
    feature, fillers = _sample_banners()
    doc = build_content("c", feature, fillers, brand_config)
    blocks = doc["sections"][1]["rows"][0]["columns"][0]["blocks"]
    image_blocks = [b for b in blocks if b["type"] == "image"]
    # Tamper Mystery link
    image_blocks[-1]["image"]["link"] = "https://example.com/wrong"
    structural, _, _, _ = cheap_checks(doc, 5, brand_config)
    assert any("Mystery" in s for s in structural)


def test_audit_series_writes_report(brand_config, tmp_path: Path) -> None:
    feature, fillers = _sample_banners()
    doc = build_content("c", feature, fillers, brand_config)
    series_dir = tmp_path / "campaigns" / "test-series"
    series_dir.mkdir(parents=True)
    (series_dir / "day01_butter-waffle.json").write_text(json.dumps(doc, indent=2))

    report = audit_series(
        series_name="test-series",
        content_dir=series_dir,
        brand=brand_config,
        shopify=None,  # skip medium checks
    )
    assert report.passed
    assert report.days_checked == [1]


def test_render_markdown_report_smoke(brand_config) -> None:
    from fms_campaigns.models import AuditReport, LinkCheckResult

    report = AuditReport(
        series="x", days_checked=[1, 2], total_links=10,
        failed_links=[
            LinkCheckResult(url="https://x/c/h", status=404, is_ok=False, note="404")
        ],
    )
    md = render_markdown_report(report)
    assert "# Audit report" in md
    assert "FAILED" in md
    assert "404" in md
