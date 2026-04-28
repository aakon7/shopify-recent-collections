"""Config loader tests."""
from __future__ import annotations

import pytest

from fms_campaigns.config import BrandConfig, load_config


def test_load_fms_config(brand_config: BrandConfig) -> None:
    assert brand_config.id == "fms"
    assert brand_config.shopify_domain == "fabricmegastore.com"
    assert brand_config.timezone == "America/Chicago"
    assert len(brand_config.block_ids.images) == 19
    assert brand_config.block_ids.mystery == "69d40a37000a70c653a31c5f"
    assert brand_config.banner_sizes.landscape_height == 378
    assert brand_config.banner_sizes.portrait_height == 566
    assert brand_config.template.mystery_image_id == "69d40c6a9dc20b9a99269d2b"


def test_resize_height_derivation(brand_config: BrandConfig) -> None:
    assert brand_config.banner_sizes.resize_height(378) == pytest.approx(355.764706, abs=1e-5)
    assert brand_config.banner_sizes.resize_height(566) == pytest.approx(532.705882, abs=1e-5)
    assert brand_config.banner_sizes.resize_height(565) == pytest.approx(531.764706, abs=1e-5)


def test_missing_brand_raises(project_root) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(brand="nonexistent", project_root=project_root)


def test_secrets_loaded_from_env(brand_config: BrandConfig) -> None:
    assert brand_config.secrets.omnisend_api_key == "test-key"
    assert brand_config.secrets.anthropic_api_key is None
