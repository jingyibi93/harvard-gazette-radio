#!/usr/bin/env python3
"""Keep only files referenced by the latest ten public episodes."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"


def relative(value: str) -> str:
    return value.removeprefix("./")


def main() -> int:
    episodes_dir = SITE / "episodes"
    index = json.loads((episodes_dir / "index.json").read_text(encoding="utf-8"))[:10]
    keep = {"episodes/index.json", "episodes/latest.json"}
    for item in index:
        path = relative(str(item["path"]))
        keep.add(path)
        payload = json.loads((SITE / path).read_text(encoding="utf-8"))
        for story in payload.get("stories", []):
            if story.get("image"):
                keep.add(relative(str(story["image"])).split("?", 1)[0])
        for value in payload.get("audio", {}).values():
            keep.add(relative(str(value)).split("?", 1)[0])
        for transcript in payload.get("transcript", {}).values():
            keep.add(relative(str(transcript["srt"])))
            keep.add(relative(str(transcript["text"])))
    for prefix in ("episodes", "audio", "images"):
        for path in (SITE / prefix).glob("*"):
            if path.is_file() and path.relative_to(SITE).as_posix() not in keep:
                path.unlink()
                print(f"Removed obsolete {path.relative_to(SITE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
