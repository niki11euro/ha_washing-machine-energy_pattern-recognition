"""Locale-independent display formatting for Home Assistant washer predictions."""

from __future__ import annotations

from datetime import datetime
from math import ceil
from time import time
from zoneinfo import ZoneInfo


def format_finish_clock(utc_timestamp: float, time_zone: str) -> str:
    """Return a clock time, never a relative timestamp rendered by HA."""
    return datetime.fromtimestamp(utc_timestamp, ZoneInfo(time_zone)).strftime("%H:%M")


def minutes_until(utc_timestamp: float, now_timestamp: float | None = None) -> int:
    """Count down against a fixed predicted end rather than freezing for 5 minutes."""
    remaining_seconds = utc_timestamp - (time() if now_timestamp is None else now_timestamp)
    return max(0, ceil(remaining_seconds / 60))
