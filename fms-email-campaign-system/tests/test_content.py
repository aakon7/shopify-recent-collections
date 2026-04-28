"""Content builder tests + golden file."""
from __future__ import annotations

import json
from pathlib import Path

from fms_campaigns.content import build_content, get_image_blocks, image_block, mystery_block
from fms_campaigns.models import Banner

GOLDEN_DIR = Path(__file__).parent / "fixtures" / "golden"


def _sample_banners() -> tuple[Banner, list[Banner]]:
    feature = Banner(
        source_id="aaaaaaaaaaaaaaaaaaaaaaaa",
        handle="butter-waffle",
        title="Butter Waffle",
        height=566,
    )
    fillers = [
        Banner(
            source_id=f"fffffffffffffffffffffff{i:01x}",
            handle=f"filler-{i}",
            title=f"Filler {i}",
            height=378,
        )
        for i in range(18)
    ]
    return feature, fillers


def test_build_content_structure(brand_config) -> None:
    feature, fillers = _sample_banners()
    doc = build_content("test-content-id", feature, fillers, brand_config)

    assert doc["id"] == "test-content-id"
    assert "generalSettings" in doc
    assert len(doc["sections"]) == 3

    blocks = doc["sections"][1]["rows"][0]["columns"][0]["blocks"]
    image_blocks = [b for b in blocks if b.get("type") == "image"]
    menu_blocks = [b for b in blocks if b.get("type") == "menu"]
    assert len(image_blocks) == 20  # 19 banners + Mystery
    assert len(menu_blocks) == 1

    # Featured banner is at position 0
    assert image_blocks[0]["image"]["altText"] == "Butter Waffle"
    assert image_blocks[0]["image"]["height"] == 566
    assert image_blocks[0]["image"]["link"].endswith("/collections/butter-waffle")

    # Mystery is last
    last = image_blocks[-1]["image"]
    assert last["link"] == brand_config.template.mystery_product_url
    assert last["id"] == brand_config.template.mystery_image_id


def test_resize_height_derived(brand_config) -> None:
    feature, fillers = _sample_banners()
    doc = build_content("c", feature, fillers, brand_config)
    blocks = get_image_blocks(doc)
    for b in blocks[:-1]:  # skip Mystery (has fixed 531.75)
        img = b["image"]
        expected = brand_config.banner_sizes.resize_height(img["height"])
        assert abs(img["resizeHeight"] - expected) < 1e-5


def test_block_ids_match_template(brand_config) -> None:
    feature, fillers = _sample_banners()
    doc = build_content("c", feature, fillers, brand_config)
    blocks = get_image_blocks(doc)
    ids_in_doc = [b["id"] for b in blocks]
    expected = [*brand_config.block_ids.images, brand_config.block_ids.mystery]
    assert ids_in_doc == expected


def test_unsubscribe_link_in_footer(brand_config) -> None:
    feature, fillers = _sample_banners()
    doc = build_content("c", feature, fillers, brand_config)
    footer_blocks = doc["sections"][2]["rows"][0]["columns"][0]["blocks"]
    text_blob = "".join(b.get("text", "") for b in footer_blocks if b.get("type") == "text")
    assert "[[unsubscribe_link]]" in text_blob


def test_wrong_filler_count_raises(brand_config) -> None:
    feature, fillers = _sample_banners()
    import pytest

    with pytest.raises(ValueError):
        build_content("c", feature, fillers[:5], brand_config)


def test_golden_file(brand_config) -> None:
    """Byte-stable output: build → JSON should match the checked-in golden file."""
    feature, fillers = _sample_banners()
    doc = build_content("test-content-id", feature, fillers, brand_config)

    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    golden_path = GOLDEN_DIR / "day_sample.json"
    actual = json.dumps(doc, indent=2, sort_keys=True)

    if not golden_path.exists():
        # First run materializes the golden. Subsequent runs verify.
        golden_path.write_text(actual)
    expected = golden_path.read_text()
    assert actual == expected, "Golden file mismatch — review changes and regenerate if intended"


def test_image_block_link_uses_brand_domain(brand_config) -> None:
    banner = Banner(source_id="x" * 24, handle="h", title="T", height=378)
    block = image_block("blockid", banner, brand_config)
    assert block["image"]["link"] == "https://fabricmegastore.com/collections/h"
    assert block["image"]["source"] == f"/image/newsletter/{'x' * 24}"


def test_mystery_block_constants(brand_config) -> None:
    block = mystery_block(brand_config)
    assert block["id"] == "69d40a37000a70c653a31c5f"
    assert block["image"]["id"] == "69d40c6a9dc20b9a99269d2b"
    assert "/products/" in block["image"]["link"]
