"""Match: OCR + fuzzy-match each banner to a Shopify collection handle."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from loguru import logger
from rich.console import Console
from rich.table import Table
from sqlmodel import Session, select

from ..db import CachedCollection, CollectionMatch, Image, init_db
from ..ocr import CachedCollectionRow, match_banner, ocr_banner
from ..services import Services

console = Console()


def _refresh_collection_cache(services: Services, session: Session) -> list[CachedCollectionRow]:
    rows = session.exec(
        select(CachedCollection).where(CachedCollection.brand_id == services.config.id)
    ).all()
    if not rows:
        console.print(
            "[yellow]Warning: no cached collections in DB. Run "
            "`fms-campaigns brand refresh-collections` first.[/yellow]"
        )
        return []
    return [CachedCollectionRow(handle=r.handle, title=r.title) for r in rows]


def run(services: Services, *, series: str, auto: bool, threshold: float) -> None:
    config = services.config
    engine = init_db(config.paths.state_db)

    table = Table(title=f"Match — {series}")
    table.add_column("File")
    table.add_column("OCR (truncated)")
    table.add_column("→ Handle")
    table.add_column("Conf")
    table.add_column("Method")
    table.add_column("Action")

    with Session(engine) as session:
        collections = _refresh_collection_cache(services, session)
        if not collections:
            return
        handles_by_handle = {c.handle: c.title for c in collections}

        unmatched = session.exec(
            select(Image)
            .where(Image.brand_id == config.id)
            .where(~Image.id.in_(select(CollectionMatch.image_id)))
        ).all()

        if not unmatched:
            console.print("[green]All images already matched.[/green]")
            return

        low_conf_count = 0
        for img in unmatched:
            try:
                ocr_text = ocr_banner(Path(img.source_path))
            except RuntimeError as e:
                logger.error(f"OCR unavailable: {e}")
                console.print(f"[red]{e}[/red]")
                return

            result = match_banner(
                filename=img.filename,
                ocr_text=ocr_text,
                collections=collections,
                threshold=threshold,
                handles_by_handle=handles_by_handle,
            )

            ocr_short = (result.ocr or "").replace("\n", " ")[:40]
            handle = result.match_handle or "—"
            confidence = result.confidence

            if auto and confidence >= threshold and result.match_handle:
                session.add(
                    CollectionMatch(
                        image_id=img.id,
                        brand_id=config.id,
                        handle=result.match_handle,
                        title=result.match_title or "",
                        match_method=result.method,
                        confidence=confidence,
                        last_verified_at=datetime.utcnow(),
                    )
                )
                session.commit()
                action = "auto-saved"
            else:
                action = "REVIEW" if confidence < threshold else "(--no-auto)"
                low_conf_count += 1

            table.add_row(
                img.filename, ocr_short or "(none)", handle, f"{confidence:.2f}",
                result.method, action,
            )

    console.print(table)
    if low_conf_count:
        console.print(
            f"[yellow]{low_conf_count} matches need human review. "
            f"Use `fms-campaigns review --series {series}` (not yet implemented in v1).[/yellow]"
        )
