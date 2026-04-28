"""Domain types used across the pipeline. Distinct from db.py — these are
the in-memory shapes (immutable, validated) we pass between modules.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Banner(BaseModel):
    """A banner image, post-ingest, post-match. Used by the content builder."""

    source_id: str  # Omnisend image library id
    handle: str  # Shopify collection handle
    title: str  # Display title (used as alt text)
    height: int  # Source height; 378 (landscape) or 566 (portrait)


class MatchCandidate(BaseModel):
    handle: str
    title: str
    score: float


class MatchResult(BaseModel):
    file: str
    ocr: str
    match_handle: str | None
    match_title: str | None
    confidence: float
    method: Literal["ocr", "filename", "manual", "fuzzy"] = "ocr"
    top3: list[MatchCandidate] = Field(default_factory=list)


class LinkCheckResult(BaseModel):
    url: str
    status: int | None
    final_url: str | None = None
    products_count: int = 0
    is_ok: bool
    note: str = ""


class WithinEmailDuplicate(BaseModel):
    day: int
    handle: str
    positions: list[int]


class ResizeMismatch(BaseModel):
    day: int
    position: int
    alt_text: str
    actual: float
    expected: float


class AuditReport(BaseModel):
    series: str
    days_checked: list[int]
    total_links: int
    failed_links: list[LinkCheckResult] = Field(default_factory=list)
    empty_collections: list[LinkCheckResult] = Field(default_factory=list)
    within_email_dupes: list[WithinEmailDuplicate] = Field(default_factory=list)
    resize_mismatches: list[ResizeMismatch] = Field(default_factory=list)
    block_count_errors: list[str] = Field(default_factory=list)
    structural_errors: list[str] = Field(default_factory=list)
    art_mismatches: list[dict] = Field(default_factory=list)  # only populated by --deep

    @property
    def passed(self) -> bool:
        return not (
            self.failed_links
            or self.empty_collections
            or self.within_email_dupes
            or self.resize_mismatches
            or self.block_count_errors
            or self.structural_errors
        )
