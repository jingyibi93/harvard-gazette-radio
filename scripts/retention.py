#!/usr/bin/env python3
"""Rolling-date retention rules for public radio episodes."""

from __future__ import annotations

import datetime as dt


RETENTION_DAYS = 10


def recent_episodes(items: list[dict], days: int = RETENTION_DAYS) -> list[dict]:
    dated: list[tuple[dt.date, dict]] = []
    for item in items:
        try:
            dated.append((dt.date.fromisoformat(str(item["id"])), item))
        except (KeyError, TypeError, ValueError):
            continue
    if not dated:
        return []
    newest = max(value for value, _ in dated)
    cutoff = newest - dt.timedelta(days=days - 1)
    return [
        item
        for value, item in sorted(dated, key=lambda pair: pair[0], reverse=True)
        if cutoff <= value <= newest
    ]
