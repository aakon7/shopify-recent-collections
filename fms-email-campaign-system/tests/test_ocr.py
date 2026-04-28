"""OCR + matching tests. Tesseract calls are not exercised here — those need
real Tesseract installed and would slow the suite. Pure-Python helpers only.
"""
from __future__ import annotations

from fms_campaigns.ocr import CachedCollectionRow, match_banner, score_match, slugify_filename


def test_slugify_filename_strips_known_suffixes() -> None:
    assert (
        slugify_filename("Cottagecore_Spring_Floral_Fabric_Collection_Banner.jpg")
        == "cottagecore-spring-floral"
    )
    assert (
        slugify_filename("Email-Banner-Sunhat_Garden_800x800.png")
        == "sunhat-garden"
    )
    assert slugify_filename("Plain_Name.jpg") == "plain-name"


def test_score_match_strong_containment() -> None:
    score = score_match("Butter Waffle Fabric Collection", "Butter Waffle")
    assert score > 0.7


def test_score_match_weak_unrelated() -> None:
    score = score_match("Octopus Garden Fabric Collection", "Floral Wildflowers")
    assert score < 0.3


def test_match_banner_filename_fallback() -> None:
    collections = [
        CachedCollectionRow(handle="butter-waffle", title="Butter Waffle"),
        CachedCollectionRow(handle="english-garden", title="English Garden"),
    ]
    # OCR returns nothing → must fall back to filename
    result = match_banner(
        filename="english_garden_Fabric_Collection_Banner.png",
        ocr_text="",
        collections=collections,
        threshold=0.3,
    )
    assert result.match_handle == "english-garden"
    assert result.method == "filename"


def test_match_banner_strong_ocr_match() -> None:
    collections = [
        CachedCollectionRow(handle="butter-waffle", title="Butter Waffle"),
        CachedCollectionRow(handle="english-garden", title="English Garden"),
    ]
    result = match_banner(
        filename="anything.png",
        ocr_text="Butter Waffle Fabric Collection",
        collections=collections,
        threshold=0.3,
    )
    assert result.match_handle == "butter-waffle"
    assert result.method == "ocr"
    assert result.confidence > 0.5


def test_match_banner_no_collections_safe() -> None:
    result = match_banner(filename="x.png", ocr_text="anything", collections=[], threshold=0.3)
    assert result.match_handle is None
    assert result.confidence == 0.0
