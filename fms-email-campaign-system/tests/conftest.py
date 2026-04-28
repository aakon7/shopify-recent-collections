"""Shared pytest fixtures."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from fms_campaigns.config import BrandConfig, load_config


PROJECT_ROOT = Path(__file__).parent.parent


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """Copy config/fms.toml into a temp dir so each test has isolated state."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    shutil.copy(PROJECT_ROOT / "config" / "fms.toml", config_dir / "fms.toml")
    return tmp_path


@pytest.fixture
def brand_config(project_root: Path, monkeypatch: pytest.MonkeyPatch) -> BrandConfig:
    monkeypatch.setenv("FMS_BRAND", "fms")
    monkeypatch.setenv("OMNISEND_API_KEY", "test-key")
    monkeypatch.setenv("FMS_STATE_DIR", str(project_root / ".fms"))
    return load_config(brand="fms", project_root=project_root)
