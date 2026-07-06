#!/usr/bin/env python3
"""Repair known legacy story titles without changing story order or links."""

from __future__ import annotations

import json
import re
from pathlib import Path


SITE = Path(__file__).resolve().parent.parent / "site"
TITLES = {
    "https://magazine.hms.harvard.edu/articles/covert-consciousness-dilemma": "The Covert Consciousness Dilemma",
    "https://hsph.harvard.edu/news/ebolas-spread-fueled-by-cuts-in-humanitarian-aid/": "Ebola’s spread fueled by cuts in humanitarian aid",
    "https://news.harvard.edu/gazette/story/2026/06/its-good-to-break-a-sweat-but-dont-sweat-the-details/": "It’s good to break a sweat, but don’t sweat the details",
    "https://current.fas.harvard.edu/stories/how-modern-life-compounds-ancient-struggle-belong": "How modern life compounds ancient struggle to belong",
    "https://news.harvard.edu/gazette/story/2026/06/dont-believe-everything-you-hear-or-read/": "Don’t believe everything you hear — or read",
    "https://hsph.harvard.edu/news/how-to-get-more-protein-and-fiber-from-a-single-sweet-spot-food/": "How to get more protein and fiber from a single ‘sweet-spot’ food",
    "https://hms.harvard.edu/news/new-tool-helps-uncover-rare-genetic-mutations-common-diseases-including-parkinsons": "New tool helps uncover rare genetic mutations in common diseases, including Parkinson’s",
    "https://hls.harvard.edu/today/america-unfinished-explores-the-state-of-the-nation-at-250/": "America Unfinished explores the state of the nation at 250",
    "https://news.harvard.edu/gazette/story/2026/06/ai-has-lots-of-people-digging-out-their-ipods/": "You take AI, I’ll take my iPod (if I can find it)",
}
PROGRAM_TITLES = {
    "2026-06-25": "Covert Consciousness, Ebola, and the Truth About Exercise",
    "2026-06-26": "Belonging, Unreliable Narratives, and Nutritional Balance",
    "2026-07-01": "Parkinson’s, America Unfinished, and the Tech Backlash",
    "2026-07-02": "Extreme Heat, Campus Memories, and the History of the Dollar",
    "2026-07-03": "The Declaration in Print, a Nobel Laureate’s WNBA Assist, and the Evolution of Men’s Suits",
}


def episode_identifier(path: Path, payload: dict) -> str:
    if path.stem != "latest":
        return path.stem
    match = re.fullmatch(
        r"(\d{4})年(\d{1,2})月(\d{1,2})日",
        str(payload.get("date", "")).strip(),
    )
    if not match:
        return ""
    year, month, day = (int(value) for value in match.groups())
    return f"{year:04d}-{month:02d}-{day:02d}"


def main() -> int:
    changed = 0
    for path in sorted((SITE / "episodes").glob("*.json")):
        if path.name == "index.json":
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        dirty = False
        identifier = episode_identifier(path, payload)
        program_title = PROGRAM_TITLES.get(identifier)
        if program_title and payload.get("title", {}).get("en") != program_title:
            payload["title"]["en"] = program_title
            dirty = True
        for story in payload.get("stories", []):
            title = TITLES.get(str(story.get("url", "")))
            if title and story.get("en") != title:
                story["en"] = title
                dirty = True
        if dirty:
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            changed += 1
    index_path = SITE / "episodes" / "index.json"
    if index_path.is_file():
        index_payload = json.loads(index_path.read_text(encoding="utf-8"))
        dirty = False
        for item in index_payload:
            program_title = PROGRAM_TITLES.get(str(item.get("id", "")))
            if program_title and item.get("title", {}).get("en") != program_title:
                item["title"]["en"] = program_title
                dirty = True
        if dirty:
            index_path.write_text(
                json.dumps(index_payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            changed += 1
    print(f"Repaired English story titles in {changed} episode files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
