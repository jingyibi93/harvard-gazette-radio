#!/usr/bin/env python3
"""Publish a generated Markdown brief as a Harvard Radio web episode."""

from __future__ import annotations

import argparse
import json
import re
import urllib.parse
from pathlib import Path


def section(markdown: str, heading: str, next_heading: str | None = None) -> str:
    start = re.search(rf"(?im)^##\s+{re.escape(heading)}.*$", markdown)
    if not start:
        raise ValueError(f"Missing section: {heading}")
    tail = markdown[start.end():]
    if next_heading:
        end = re.search(rf"(?im)^##\s+{re.escape(next_heading)}.*$", tail)
        if end:
            tail = tail[:end.start()]
    return tail.strip()


def spoken(text: str) -> str:
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*_>`#]+", "", text)
    text = re.sub(r"^\s*[-+]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(
        r"\((?:背景音乐|音乐|Background Music|Music).*?\)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"(?im)^\s*[（(]?(?:开场音乐|背景音乐|音乐|Background Music|Music)[^。\n]*[）)]?\s*$",
        "",
        text,
    )
    text = re.sub(r"(?im)^\s*(?:主持人|主播|Host|Presenter)\s*[：:]\s*", "", text)
    text = re.sub(
        r"(?:我是(?:您的|你们的)?(?:主持人|主播|助手)[^。！？.!?]*[。！？.!?]?)",
        "",
        text,
    )
    text = re.sub(
        r"(?:I(?:['’]m| am) (?:your |the )?(?:host|presenter)[^.!?]*[.!?]?)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_stories(markdown: str) -> list[tuple[str, str, str]]:
    lines = markdown.splitlines()
    stories: list[tuple[str, str, str]] = []
    labeled_source = re.compile(r"\*\*来源：\*\*\s+\[([^\]]+)\]\((https?://[^)]+)\)")
    source_link = re.compile(
        r"\[([^\]]*(?:来源|Source)[^\]]*)\]\((https?://[^)]+)\)",
        re.IGNORECASE,
    )
    for index, line in enumerate(lines):
        source = labeled_source.search(line) or source_link.search(line)
        if not source:
            continue
        title = ""
        for candidate in reversed(lines[max(0, index - 8):index]):
            heading = re.match(r"^###\s+(?:\d+\.\s+)?(.+?)\s*$", candidate)
            bold = re.match(r"^\*\*(?!为何重要|来源)(.+?)\*\*\s*$", candidate)
            match = heading or bold
            if match:
                title = match.group(1).strip()
                break
        if title:
            stories.append((title, source.group(1), source.group(2)))
    return stories[:3]


def public_url(url: str) -> str:
    """Remove newsletter recipient tracking before a URL reaches the public site."""
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def publish(
    brief: Path,
    radio_dir: Path,
    episode_id: str = "latest",
    english_title: str = "",
    email_subject: str = "",
    set_latest: bool = False,
    update_index: bool = False,
) -> dict:
    markdown = brief.read_text(encoding="utf-8")
    title_match = re.search(r"(?m)^#\s+(.+)$", markdown)
    date_match = re.search(r"\*\*日期：\*\*\s*(.+)", markdown)
    if not date_match and title_match:
        date_match = re.search(r"(20\d{2}年\d{1,2}月\d{1,2}日)", title_match.group(1))
    story_matches = extract_stories(markdown)
    if not title_match or not date_match or not story_matches:
        raise ValueError("The brief does not contain the expected title, date, and stories.")

    zh = spoken(section(markdown, "中文电台 Broadcast", "English Radio Broadcast"))
    en = spoken(section(markdown, "English Radio Broadcast"))
    episode_dir = radio_dir / "episodes"
    audio_dir = radio_dir / "audio"
    episode_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)
    (audio_dir / f"{episode_id}-zh.txt").write_text(zh + "\n", encoding="utf-8")
    (audio_dir / f"{episode_id}-en.txt").write_text(en + "\n", encoding="utf-8")

    stories = [
        {"zh": title, "en": source, "source": source, "url": public_url(url)}
        for title, source, url in story_matches[:3]
    ]
    audio_version = re.sub(r"\D", "", date_match.group(1)) or "latest"
    payload = {
        "date": date_match.group(1).strip(),
        "title": {
            "zh": title_match.group(1).replace("哈佛公报：", ""),
            "en": english_title or title_match.group(1).replace("哈佛公报：", ""),
        },
        "stories": stories,
        "audio": {
            "zh": f"./audio/{episode_id}-zh.m4a?v={audio_version}",
            "en": f"./audio/{episode_id}-en.m4a?v={audio_version}",
        },
        "transcript": {
            "zh": {
                "srt": f"./audio/{episode_id}-zh.srt",
                "text": f"./audio/{episode_id}-zh.txt",
            },
            "en": {
                "srt": f"./audio/{episode_id}-en.srt",
                "text": f"./audio/{episode_id}-en.txt",
            },
        },
    }
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    (episode_dir / f"{episode_id}.json").write_text(serialized, encoding="utf-8")
    if set_latest:
        (episode_dir / "latest.json").write_text(serialized, encoding="utf-8")
    if update_index:
        index_path = episode_dir / "index.json"
        items = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else []
        items = [item for item in items if item.get("id") != episode_id]
        items.append(
            {
                "id": episode_id,
                "date": payload["date"],
                "title": payload["title"],
                "path": f"./episodes/{episode_id}.json",
                "emailSubject": email_subject or english_title,
            }
        )
        items.sort(key=lambda item: item["id"], reverse=True)
        index_path.write_text(
            json.dumps(items, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(f"Published episode data to {episode_dir / f'{episode_id}.json'}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("brief", type=Path)
    parser.add_argument("radio_dir", type=Path)
    parser.add_argument("--episode-id", default="latest")
    parser.add_argument("--english-title", default="")
    parser.add_argument("--email-subject", default="")
    parser.add_argument("--set-latest", action="store_true")
    parser.add_argument("--update-index", action="store_true")
    args = parser.parse_args()
    publish(
        args.brief,
        args.radio_dir,
        args.episode_id,
        args.english_title,
        args.email_subject,
        args.set_latest,
        args.update_index,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
