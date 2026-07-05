#!/usr/bin/env python3
"""Backfill missing Harvard Gazette Radio episodes from the last ten days."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from email.utils import parsedate_to_datetime
from pathlib import Path

import daily_brief
import generate_daily
import publish_radio_episode


ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
SCRIPTS = ROOT / "scripts"


def main() -> int:
    messages = daily_brief.relevant(daily_brief.read_163(10))
    messages.sort(
        key=lambda item: parsedate_to_datetime(str(item["date"])),
        reverse=True,
    )
    index_path = SITE / "episodes" / "index.json"
    existing_index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.is_file() else []
    published_subjects = {
        str(entry.get("emailSubject", "")).strip()
        for entry in existing_index
        if entry.get("emailSubject")
    }
    seen: set[str] = set()
    for item in messages:
        subject = str(item["subject"]).strip()
        if subject in published_subjects:
            print(f"Newsletter already exists in history; skipping: {subject}")
            continue
        identifier = generate_daily.episode_id(item)
        if identifier in seen:
            continue
        seen.add(identifier)
        episode_path = SITE / "episodes" / f"{identifier}.json"
        if episode_path.exists():
            print(f"Episode {identifier} already exists; skipping.")
            continue
        with tempfile.TemporaryDirectory(prefix=f"harvard-radio-{identifier}-") as temp_dir:
            brief = Path(temp_dir) / f"{identifier}.md"
            packet = daily_brief.source_packet([item], True)
            brief.write_text(
                daily_brief.call_agnes(packet, broadcast_date=identifier) + "\n",
                encoding="utf-8",
            )
            publish_radio_episode.publish(
                brief,
                SITE,
                identifier,
                english_title=str(item["subject"]),
                email_subject=str(item["subject"]),
                update_index=True,
            )
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "fetch_story_images.py"),
                    str(brief),
                    str(SITE),
                    "--episode-id",
                    identifier,
                ],
                check=True,
            )
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "render_radio_audio.py"),
                    str(SITE),
                    "--episode-id",
                    identifier,
                    "--music",
                    str(ROOT / "assets" / "music" / "window-on-the-world.mp3"),
                ],
                check=True,
            )
        generate_daily.validate_episode(identifier)
        published_subjects.add(subject)
        print(f"Backfilled and validated episode {identifier}.")
    generate_daily.trim_archive()
    index = json.loads((SITE / "episodes" / "index.json").read_text(encoding="utf-8"))
    print(f"History now contains {len(index)} episodes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
