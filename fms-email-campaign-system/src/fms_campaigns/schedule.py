"""Scheduling helpers — turn local wall times into RFC 3339 UTC.

Always use zoneinfo, never hardcode CDT/CST offsets.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def local_to_utc_iso(date_str: str, time_str: str, tz: str) -> str:
    """('2026-05-04', '09:00', 'America/Chicago') → '2026-05-04T14:00:00Z' (in CDT)."""
    naive = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    aware = naive.replace(tzinfo=ZoneInfo(tz))
    utc = aware.astimezone(ZoneInfo("UTC"))
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def schedule_series_dates(
    start_date: str, time_str: str, tz: str, days: int
) -> list[str]:
    """Return list of UTC ISO timestamps, one per day, starting at start_date local time."""
    out: list[str] = []
    for offset in range(days):
        naive_date = datetime.strptime(start_date, "%Y-%m-%d") + timedelta(days=offset)
        out.append(local_to_utc_iso(naive_date.strftime("%Y-%m-%d"), time_str, tz))
    return out
