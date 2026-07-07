#!/usr/bin/env python3
"""Generate and validate one new Harvard Gazette Radio episode."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import datetime as dt
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import daily_brief
import publish_radio_episode
import retention


ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
SCRIPTS = ROOT / "scripts"


def message_time(item: dict[str, object]) -> dt.datetime:
    value = parsedate_to_datetime(str(item["date"]))
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo("America/New_York"))
    return value


def expected_episode_id() -> str:
    beijing_today = dt.datetime.now(ZoneInfo("Asia/Shanghai")).date()
    return (beijing_today + dt.timedelta(days=1)).isoformat()


def read_archive() -> list[dict[str, object]]:
    index_path = SITE / "episodes" / "index.json"
    return json.loads(index_path.read_text(encoding="utf-8")) if index_path.is_file() else []


def is_published(item: dict[str, object], identifier: str, archive: list[dict[str, object]]) -> bool:
    subject = str(item.get("subject", "")).strip()
    if (SITE / "episodes" / f"{identifier}.json").exists():
        return True
    return any(str(entry.get("emailSubject", "")).strip() == subject for entry in archive)


def report_no_new_mail(identifier: str, reason: str) -> int:
    print(f"No new newsletter is available for episode {identifier}.")
    print(f"Reason: {reason}")
    print("Keeping the previously published episode. No files were overwritten.")
    return 0


def newest_message() -> dict[str, object]:
    messages = daily_brief.relevant(daily_brief.read_163(3))
    if not messages:
        raise RuntimeError("No Harvard Gazette email arrived in the last three days.")
    return max(messages, key=message_time)


def episode_id(item: dict[str, object]) -> str:
    received = parsedate_to_datetime(str(item["date"]))
    if received.tzinfo is None:
        received = received.replace(tzinfo=ZoneInfo("America/New_York"))
    beijing_date = received.astimezone(ZoneInfo("Asia/Shanghai")).date()
    return (beijing_date + dt.timedelta(days=1)).isoformat()


def trim_archive() -> None:
    path = SITE / "episodes" / "index.json"
    items = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(
        json.dumps(retention.recent_episodes(items), ensure_ascii=False, indent=2) + "\n",
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
    target = expected_episode_id()
    archive = read_archive()
    messages = sorted(
        daily_brief.relevant(daily_brief.read_163(3)),
        key=message_time,
        reverse=True,
    )
    item = next(
        (
            candidate
            for candidate in messages
            if not is_published(candidate, episode_id(candidate), archive)
        ),
        None,
    )
    if item is None:
        if (SITE / "episodes" / f"{target}.json").exists():
            print(f"Episode {target} already exists; keeping the published version.")
            return 0
        reason = (
            "最近三天没有匹配 gazette@u.harvard.edu 的邮件。"
            if not messages
            else "最近三天匹配到的 Harvard Gazette 邮件都已经发布过，没有新的未发布邮件。"
        )
        return report_no_new_mail(target, reason)

    identifier = episode_id(item)

    with tempfile.TemporaryDirectory(prefix="harvard-radio-") as temp_dir:
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
