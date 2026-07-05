#!/usr/bin/env python3
"""Generate and validate one new Harvard Gazette Radio episode."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from email.utils import parsedate_to_datetime
from pathlib import Path

import daily_brief
import publish_radio_episode


ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
SCRIPTS = ROOT / "scripts"


def newest_message() -> dict[str, object]:
    messages = daily_brief.relevant(daily_brief.read_163(3))
    if not messages:
        raise RuntimeError("No Harvard Gazette email arrived in the last three days.")
    return max(messages, key=lambda item: parsedate_to_datetime(str(item["date"])))


def episode_id(item: dict[str, object]) -> str:
    return parsedate_to_datetime(str(item["date"])).date().isoformat()


def trim_archive() -> None:
    path = SITE / "episodes" / "index.json"
    items = json.loads(path.read_text(encoding="utf-8"))
    items.sort(key=lambda item: item["id"], reverse=True)
    path.write_text(
        json.dumps(items[:10], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def validate_episode(identifier: str) -> None:
    path = SITE / "episodes" / f"{identifier}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    stories = payload.get("stories", [])
    if len(stories) != 3:
        raise RuntimeError("Refusing to publish: the episode must contain exactly three stories.")
    for index, story in enumerate(stories, 1):
        url = str(story.get("url", ""))
        image = str(story.get("image", ""))
        if not url.startswith("https://") or "?" in url or "#" in url:
            raise RuntimeError(f"Refusing to publish: story {index} has an unsafe source URL.")
        english_title = str(story.get("en", "")).strip().casefold()
        if english_title in {"source", "source link", "来源", "来源链接"}:
            raise RuntimeError(f"Refusing to publish: story {index} has no valid English title.")
        if not image:
            raise RuntimeError(f"Refusing to publish: story {index} has no verified cover image.")
        image_path = SITE / image.removeprefix("./")
        if not image_path.is_file() or image_path.stat().st_size < 10_000:
            raise RuntimeError(f"Refusing to publish: story {index} cover image is invalid.")
    for language in ("zh", "en"):
        audio = SITE / "audio" / f"{identifier}-{language}.m4a"
        subtitle = SITE / "audio" / f"{identifier}-{language}.srt"
        if not audio.is_file() or audio.stat().st_size < 50_000 or not subtitle.is_file():
            raise RuntimeError(f"Refusing to publish: {language} audio or subtitles are missing.")


def main() -> int:
    item = newest_message()
    identifier = episode_id(item)
    existing = SITE / "episodes" / f"{identifier}.json"
    if existing.exists():
        print(f"Episode {identifier} already exists; keeping the published version.")
        return 0

    with tempfile.TemporaryDirectory(prefix="harvard-radio-") as temp_dir:
        brief = Path(temp_dir) / f"{identifier}.md"
        packet = daily_brief.source_packet([item], True)
        brief.write_text(daily_brief.call_agnes(packet) + "\n", encoding="utf-8")
        publish_radio_episode.publish(
            brief,
            SITE,
            identifier,
            english_title=str(item["subject"]),
            email_subject=str(item["subject"]),
            set_latest=True,
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
                "--set-latest",
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
    validate_episode(identifier)
    trim_archive()
    print(f"Episode {identifier} passed validation and is ready to publish.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
