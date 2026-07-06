#!/usr/bin/env python3
"""Migrate legacy email-day episodes to the following Beijing morning."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
EPISODES = ROOT / "site" / "episodes"
POLICY = "next-beijing-morning"


def display_date(identifier: str) -> str:
    value = dt.date.fromisoformat(identifier)
    return f"{value.year}年{value.month}月{value.day}日"


def main() -> int:
    index_path = EPISODES / "index.json"
    if not index_path.is_file():
        print("No episode index found; nothing to migrate.")
        return 0

    index = json.loads(index_path.read_text(encoding="utf-8"))
    migrated: list[tuple[dict, dict, Path, Path]] = []
    changed = 0
    for item in index:
        source_path = ROOT / "site" / str(item["path"]).removeprefix("./")
        payload = json.loads(source_path.read_text(encoding="utf-8"))
        old_id = str(item["id"])
        if payload.get("datePolicy") == POLICY:
            new_id = old_id
        else:
            new_id = (dt.date.fromisoformat(old_id) + dt.timedelta(days=1)).isoformat()
            changed += 1
        payload["date"] = display_date(new_id)
        payload["datePolicy"] = POLICY
        migrated_item = {
            **item,
            "id": new_id,
            "date": payload["date"],
            "path": f"./episodes/{new_id}.json",
        }
        destination = EPISODES / f"{new_id}.json"
        migrated.append((migrated_item, payload, source_path, destination))

    migrated.sort(key=lambda entry: entry[0]["id"], reverse=True)
    destinations = {destination.resolve() for _, _, _, destination in migrated}
    for _, payload, _, destination in migrated:
        destination.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    for _, _, source, _ in migrated:
        if source.resolve() not in destinations and source.is_file():
            source.unlink()

    new_index = [item for item, _, _, _ in migrated]
    index_path.write_text(
        json.dumps(new_index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if migrated:
        latest_payload = migrated[0][1]
        (EPISODES / "latest.json").write_text(
            json.dumps(latest_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(f"Migrated {changed} legacy episodes to the next Beijing morning.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
