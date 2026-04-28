"""Ingest: register a folder of banner files and upload them to Omnisend.

Dedupe by sha256 against the local `image` table — re-running ingest on the
same folder is a no-op for files already uploaded.
"""
from __future__ import annotations

import hashlib
import mimetypes
from datetime import datetime
from pathlib import Path

from loguru import logger
from rich.console import Console
from rich.table import Table
from sqlmodel import Session, select

from ..db import Image, Series, init_db
from ..services import Services

console = Console()

_SUPPORTED_EXT = {".png", ".jpg", ".jpeg", ".webp"}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _peek_image(path: Path) -> tuple[int, int, str]:
    """Return (width, height, format)."""
    from PIL import Image as PILImage

    with PILImage.open(path) as img:
        return img.width, img.height, (img.format or path.suffix[1:]).lower()


def run(services: Services, *, series: str, folder: Path, dry_run: bool) -> None:
    config = services.config
    engine = init_db(config.paths.state_db)

    files = [p for p in sorted(folder.iterdir()) if p.suffix.lower() in _SUPPORTED_EXT]
    if not files:
        console.print(f"[yellow]No banner files in {folder}[/yellow]")
        return

    table = Table(title=f"Ingest — {series} ({len(files)} files)")
    table.add_column("File")
    table.add_column("sha256[:8]")
    table.add_column("WxH")
    table.add_column("Action")
    table.add_column("Source ID")

    with Session(engine) as session:
        if not session.exec(select(Series).where(Series.id == series)).first():
            session.add(
                Series(
                    id=series,
                    brand_id=config.id,
                    name=series,
                    created_at=datetime.utcnow(),
                    status="planning",
                )
            )
            session.commit()

        for path in files:
            sha = _sha256(path)
            existing = session.exec(select(Image).where(Image.sha256 == sha)).first()

            if existing:
                table.add_row(
                    path.name, sha[:8], f"{existing.width}x{existing.height}",
                    "skip (dup hash)", existing.id,
                )
                continue

            try:
                w, h, fmt = _peek_image(path)
            except Exception as e:
                logger.error(f"Could not read {path.name}: {e}")
                table.add_row(path.name, sha[:8], "?", f"error: {e}", "")
                continue

            if dry_run:
                table.add_row(path.name, sha[:8], f"{w}x{h}", "dry-run", "(would upload)")
                continue

            mime = mimetypes.guess_type(path.name)[0] or "image/png"
            try:
                resp = services.omnisend.upload_image(path.name, path.read_bytes(), mime)
            except Exception as e:
                logger.error(f"Upload failed for {path.name}: {e}")
                table.add_row(path.name, sha[:8], f"{w}x{h}", f"upload failed: {e}", "")
                continue

            source_id = resp.get("id") or resp.get("sourceID") or resp.get("source_id")
            if not source_id:
                logger.error(f"Unexpected upload response for {path.name}: {resp}")
                table.add_row(path.name, sha[:8], f"{w}x{h}", "no id in response", "")
                continue

            session.add(
                Image(
                    id=source_id,
                    brand_id=config.id,
                    filename=path.name,
                    sha256=sha,
                    width=w,
                    height=h,
                    image_format=fmt,
                    source_path=str(path.resolve()),
                    uploaded_at=datetime.utcnow(),
                )
            )
            session.commit()
            table.add_row(path.name, sha[:8], f"{w}x{h}", "uploaded", source_id)

    console.print(table)
