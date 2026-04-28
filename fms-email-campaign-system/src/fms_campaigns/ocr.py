"""OCR + collection matching.

Ported from reference_skill/scripts/match_banners.py with two upgrades:
- rapidfuzz instead of difflib (faster, better fuzzy)
- collection cache lives in SQLite, not collections.json on disk
- filename fallback exposed as a separate function (testable)

OCR settings that work (from references/ocr-match.md):
- Tesseract 5.x with `--psm 6` ("uniform block of text")
- Grayscale + 2x bicubic upscale before OCR
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz import fuzz

from .models import MatchCandidate, MatchResult


@dataclass(frozen=True)
class CachedCollectionRow:
    handle: str
    title: str


def ocr_banner(path: Path) -> str:
    """Run tesseract on a banner image. Returns "" on failure."""
    try:
        from PIL import Image
        import pytesseract
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(
            "OCR dependencies missing. Install with: pip install pytesseract pillow "
            "AND ensure tesseract binary is on PATH."
        ) from e

    try:
        img = Image.open(path).convert("L")
        img = img.resize((img.width * 2, img.height * 2), Image.BICUBIC)
        return pytesseract.image_to_string(img, config="--psm 6").strip()
    except Exception:
        return ""


_FILENAME_NOISE_RE = re.compile(
    r"_(800x800|\d+x\d+)$|_Fabric_Collection_Banner.*$|_?Email[-_]Banner[-_]?",
    re.IGNORECASE,
)


def slugify_filename(filename: str) -> str:
    """Filename → candidate handle. ~85% accurate on FMS naming convention."""
    stem = Path(filename).stem
    stem = _FILENAME_NOISE_RE.sub("", stem)
    return stem.lower().replace("_", "-").replace(" ", "-").strip("-")


def score_match(ocr_text: str, title: str) -> float:
    """Composite score combining containment, fuzzy ratio, and token overlap.

    Containment is weighted highest because banners often say "Collection Name
    Fabric Collection" and the title is just "Collection Name" — strong signal
    even when token overlap is partial.
    """
    if not ocr_text or not title:
        return 0.0

    ocr_lower = ocr_text.lower()
    title_lower = title.lower()

    contained = 1.0 if title_lower in ocr_lower else 0.0
    ratio = fuzz.WRatio(ocr_lower, title_lower) / 100.0
    token_set = fuzz.token_set_ratio(ocr_lower, title_lower) / 100.0

    return 0.4 * contained + 0.3 * ratio + 0.3 * token_set


def match_banner(
    filename: str,
    ocr_text: str,
    collections: list[CachedCollectionRow],
    *,
    threshold: float = 0.3,
    handles_by_handle: dict[str, str] | None = None,
) -> MatchResult:
    """Score the OCR text against every collection title; fall back to filename slug."""
    if handles_by_handle is None:
        handles_by_handle = {c.handle: c.title for c in collections}

    scored = sorted(
        ((c, score_match(ocr_text, c.title)) for c in collections),
        key=lambda x: x[1],
        reverse=True,
    )
    top3 = [
        MatchCandidate(handle=c.handle, title=c.title, score=round(s, 3))
        for c, s in scored[:3]
    ]
    best, best_score = (scored[0] if scored else (None, 0.0))

    method = "ocr"
    if best_score < threshold:
        slug = slugify_filename(filename)
        if slug in handles_by_handle:
            best = CachedCollectionRow(handle=slug, title=handles_by_handle[slug])
            best_score = 0.5  # Fallback confidence
            method = "filename"

    return MatchResult(
        file=filename,
        ocr=ocr_text[:200],
        match_handle=best.handle if best else None,
        match_title=best.title if best else None,
        confidence=round(best_score, 3),
        method=method,  # type: ignore[arg-type]
        top3=top3,
    )
