#!/usr/bin/env python3
"""Migrate legacy email-day episodes to the following Beijing morning."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
EPISODES = ROOT / "site" / "episodes"
POLICY = "next-beijing-morning"
SCRIPT_POLICY = "next-beijing-morning-spoken-date"
ASSET_POLICY = "spoken-date-assets-v1"
SCRIPT_REPLACEMENTS = {
    "2026-06-25": {
        "zh": (
            "今天是2026年6月24日，星期三。",
            "今天是2026年6月25日，星期四。",
        ),
        "en": (
            "today, June 24th, 2026.",
            "today, Thursday, June 25th, 2026.",
        ),
    },
    "2026-06-26": {
        "zh": (
            "大家好，欢迎收听今天的哈佛公报精选。",
            "大家好，欢迎收听今天的哈佛公报精选。今天是2026年6月26日，星期五。",
        ),
        "en": (
            "Welcome to today’s Harvard Gazette briefing.",
            "Welcome to today’s Harvard Gazette briefing. It is Friday, June 26th, 2026.",
        ),
    },
    "2026-07-01": {
        "zh": (
            "今天是2026年6月30日，星期二。",
            "今天是2026年7月1日，星期三。",
        ),
        "en": (
            "It is Tuesday, June 30th, 2026.",
            "It is Wednesday, July 1st, 2026.",
        ),
    },
    "2026-07-02": {
        "zh": (
            "今天是2026年7月1日，星期三。",
            "今天是2026年7月2日，星期四。",
        ),
        "en": (
            "today, July 1st, 2026.",
            "today, Thursday, July 2nd, 2026.",
        ),
    },
    "2026-07-03": {
        "zh": (
            "今天是2026年7月2日，星期四。",
            "今天是2026年7月3日，星期五。",
        ),
        "en": (
            "It is Thursday, July 2nd, 2026.",
            "It is Friday, July 3rd, 2026.",
        ),
    },
}


def display_date(identifier: str) -> str:
    value = dt.date.fromisoformat(identifier)
    return f"{value.year}年{value.month}月{value.day}日"


def update_spoken_dates(payload: dict, identifier: str) -> str | None:
    if payload.get("scriptDatePolicy") == SCRIPT_POLICY:
        return None
    replacements = SCRIPT_REPLACEMENTS.get(identifier)
    if not replacements:
        return None
    episode_stem = ""
    for language in ("zh", "en"):
        relative = str(payload["transcript"][language]["text"]).removeprefix("./")
        text_path = ROOT / "site" / relative
        text = text_path.read_text(encoding="utf-8")
        old, new = replacements[language]
        if old not in text:
            if new not in text:
                raise RuntimeError(
                    f"Could not find the legacy {language} spoken date in {text_path.name}."
                )
        else:
            text_path.write_text(text.replace(old, new, 1), encoding="utf-8")
        suffix = f"-{language}.txt"
        stem = text_path.name.removesuffix(suffix)
        if episode_stem and stem != episode_stem:
            raise RuntimeError(f"Mismatched transcript stems for episode {identifier}.")
        episode_stem = stem
    payload["scriptDatePolicy"] = SCRIPT_POLICY
    return episode_stem


def version_spoken_assets(payload: dict) -> None:
    if payload.get("assetVersionPolicy") == ASSET_POLICY:
        return
    for language, value in payload.get("audio", {}).items():
        payload["audio"][language] = f"{str(value).split('?', 1)[0]}?v={ASSET_POLICY}"
    for transcript in payload.get("transcript", {}).values():
        for kind in ("srt", "text"):
            transcript[kind] = f"{str(transcript[kind]).split('?', 1)[0]}?v={ASSET_POLICY}"
    payload["assetVersionPolicy"] = ASSET_POLICY


def payload_episode_stem(payload: dict) -> str | None:
    """Return the YYYY-MM-DD stem used by generated audio/transcript assets."""
    candidates: list[str] = []
    for value in payload.get("audio", {}).values():
        candidates.append(str(value))
    for transcript in payload.get("transcript", {}).values():
        for kind in ("srt", "text"):
            candidates.append(str(transcript.get(kind, "")))
    stems = {
        match.group(1)
        for value in candidates
        for match in [re.search(r"audio/(20\d{2}-\d{2}-\d{2})-(?:zh|en)\.", value)]
        if match
    }
    return next(iter(stems)) if len(stems) == 1 else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rerender",
        action="store_true",
        help="Regenerate audio and subtitles after spoken dates are updated.",
    )
    args = parser.parse_args()
    index_path = EPISODES / "index.json"
    if not index_path.is_file():
        print("No episode index found; nothing to migrate.")
        return 0

    index = json.loads(index_path.read_text(encoding="utf-8"))
    migrated: list[tuple[dict, dict, Path, Path]] = []
    rerender: set[str] = set()
    changed = 0
    for item in index:
        source_path = ROOT / "site" / str(item["path"]).removeprefix("./")
        payload = json.loads(source_path.read_text(encoding="utf-8"))
        old_id = str(item["id"])
        asset_stem = payload_episode_stem(payload)
        if payload.get("datePolicy") == POLICY:
            new_id = old_id
            if asset_stem and asset_stem != old_id and payload.get("scriptDatePolicy") != SCRIPT_POLICY:
                new_id = asset_stem
                changed += 1
        else:
            new_id = (dt.date.fromisoformat(old_id) + dt.timedelta(days=1)).isoformat()
            changed += 1
        payload["date"] = display_date(new_id)
        payload["datePolicy"] = POLICY
        episode_stem = update_spoken_dates(payload, new_id)
        version_spoken_assets(payload)
        if episode_stem:
            rerender.add(episode_stem)
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
    if rerender and not args.rerender:
        print(
            f"Updated spoken dates for {len(rerender)} episodes without rendering audio."
        )
    for episode_stem in sorted(rerender) if args.rerender else []:
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "render_radio_audio.py"),
                str(ROOT / "site"),
                "--episode-id",
                episode_stem,
                "--music",
                str(ROOT / "assets" / "music" / "window-on-the-world.mp3"),
            ],
            check=True,
        )
    print(f"Migrated {changed} legacy episodes to the next Beijing morning.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
