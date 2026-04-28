"""Schedule helper tests — DST-aware conversion."""
from __future__ import annotations

from fms_campaigns.schedule import local_to_utc_iso, schedule_series_dates


def test_cdt_9am_central_to_utc() -> None:
    # April 28 is in CDT (UTC-5), so 9 AM Central = 14:00 UTC
    assert local_to_utc_iso("2026-04-28", "09:00", "America/Chicago") == "2026-04-28T14:00:00Z"


def test_cst_9am_central_to_utc() -> None:
    # December 15 is in CST (UTC-6), so 9 AM Central = 15:00 UTC
    assert local_to_utc_iso("2026-12-15", "09:00", "America/Chicago") == "2026-12-15T15:00:00Z"


def test_dst_boundary_spring_forward() -> None:
    # March 8, 2026 is the day DST starts in Chicago. 9 AM is CDT = UTC-5.
    assert local_to_utc_iso("2026-03-08", "09:00", "America/Chicago") == "2026-03-08T14:00:00Z"


def test_schedule_series_dates_7_days() -> None:
    dates = schedule_series_dates("2026-04-28", "09:00", "America/Chicago", 7)
    assert len(dates) == 7
    assert dates[0] == "2026-04-28T14:00:00Z"
    assert dates[6] == "2026-05-04T14:00:00Z"


def test_schedule_series_crosses_dst_end() -> None:
    # Nov 1, 2026 is the day DST ends. Run a 3-day series across the boundary.
    # Oct 31 is CDT, Nov 1 is CST (transition at 2 AM local), Nov 2 is CST.
    dates = schedule_series_dates("2026-10-31", "09:00", "America/Chicago", 3)
    assert dates[0] == "2026-10-31T14:00:00Z"  # CDT
    assert dates[1] == "2026-11-01T15:00:00Z"  # CST (clocks fell back at 2am)
    assert dates[2] == "2026-11-02T15:00:00Z"  # CST
