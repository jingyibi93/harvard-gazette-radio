#!/usr/bin/env python3
"""Remove recipient tracking data from every public episode file."""

from __future__ import annotations

import json
import urllib.parse
from pathlib import Path


def clean_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def main() -> int:
    root = Path(__file__).resolve().parent.parent / "site" / "episodes"
    for path in sorted(root.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        payloads = data if isinstance(data, list) else [data]
        for payload in payloads:
            for story in payload.get("stories", []):
                url = story.get("url")
                if isinstance(url, str):
                    cleaned = clean_url(url)
                    if cleaned != url:
                        story["url"] = cleaned
                        changed = True
        if changed:
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"Sanitized {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
