#!/usr/bin/env python3
"""Fetch source-page cover images for the latest Harvard Radio episode."""

from __future__ import annotations

import argparse
import json
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path


class MetadataParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.images: list[str] = []
        self.content_images: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "img":
            values = {key.casefold(): value for key, value in attrs if value}
            candidate = values.get("src") or values.get("data-src")
            label = " ".join(
                values.get(key, "") for key in ("alt", "class", "id")
            ).casefold()
            if candidate and not any(
                word in label or word in candidate.casefold()
                for word in ("logo", "icon", "avatar", "spacer", ".svg", ".gif")
            ):
                self.content_images.append(candidate)
            return
        if tag != "meta":
            return
        values = {key.casefold(): value for key, value in attrs if value}
        key = (values.get("property") or values.get("name") or "").casefold()
        if key in {"og:image", "og:image:url", "twitter:image"} and values.get("content"):
            self.images.append(values["content"])


def request(url: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 HarvardGazetteRadio/1.0",
            "Accept": "text/html,application/xhtml+xml,image/avif,image/webp,image/*,*/*",
        },
    )


def source_links(markdown: str) -> list[tuple[str, str]]:
    return re.findall(r"\*\*来源：\*\*\s+\[([^\]]+)\]\((https?://[^)]+)\)", markdown)[:3]


def fetch_cover(
    url: str,
    output_base: Path,
    source_name: str,
    year_month: tuple[str, str],
) -> tuple[Path, str]:
    with urllib.request.urlopen(request(url), timeout=30) as response:
        final_url = response.geturl()
        raw = response.read(2_000_000)
        charset = response.headers.get_content_charset() or "utf-8"
    parsed_final = urllib.parse.urlparse(final_url)
    if (
        parsed_final.path.rstrip("/") == "/gazette"
        or re.fullmatch(r"/gazette/story/\d{4}/\d{2}/?", parsed_final.path)
    ):
        raise RuntimeError("link resolved to a homepage or archive instead of an article")
    parser = MetadataParser()
    parser.feed(raw.decode(charset, errors="replace"))
    candidates = parser.images + parser.content_images
    if not candidates:
        raise RuntimeError("source page has no cover image candidate")
    image = b""
    content_type = ""
    for candidate in candidates[:12]:
        image_url = urllib.parse.urljoin(final_url, candidate)
        try:
            with urllib.request.urlopen(request(image_url), timeout=30) as response:
                image = response.read(8_000_000)
                content_type = response.headers.get_content_type()
        except Exception:
            continue
        if len(image) >= 30_000 and content_type.startswith("image/"):
            break
    if len(image) < 30_000 or not content_type.startswith("image/"):
        raise RuntimeError("source page has no usable cover image")
    suffix = {
        "image/png": ".png",
        "image/webp": ".webp",
        "image/avif": ".avif",
    }.get(content_type, ".jpg")
    output = output_base.with_suffix(suffix)
    output.write_bytes(image)
    clean_url = urllib.parse.urlunparse(parsed_final._replace(query="", fragment=""))
    return output, clean_url


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("brief", type=Path)
    parser.add_argument("radio_dir", type=Path)
    parser.add_argument("--episode-id", default="latest")
    parser.add_argument("--set-latest", action="store_true")
    args = parser.parse_args()

    episode_path = args.radio_dir / "episodes" / f"{args.episode_id}.json"
    episode = json.loads(episode_path.read_text(encoding="utf-8"))
    links = [
        (str(story.get("source", "The Harvard Gazette")), str(story.get("url", "")))
        for story in episode.get("stories", [])
        if story.get("url")
    ][:3]
    date_match = re.search(r"(\d{4})年(\d{1,2})月", episode.get("date", ""))
    year_month = (
        date_match.group(1),
        date_match.group(2).zfill(2),
    ) if date_match else ("2026", "07")
    image_dir = args.radio_dir / "images"
    image_dir.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    for index, ((source_name, url), story) in enumerate(zip(links, episode["stories"]), 1):
        try:
            output, final_url = fetch_cover(
                url,
                image_dir / f"{args.episode_id}-story-{index}",
                source_name,
                year_month,
            )
        except Exception as exc:
            print(f"Story {index}: no cover downloaded ({exc})")
            failures.append(f"story {index}: {exc}")
            continue
        story["image"] = f"./images/{output.name}"
        story["url"] = final_url
        host = urllib.parse.urlparse(final_url).netloc
        story["source"] = {
            "news.harvard.edu": "The Harvard Gazette",
            "current.fas.harvard.edu": "Harvard Faculty of Arts and Sciences",
        }.get(host, source_name)
        print(f"Story {index}: downloaded {output.name}")

    episode_path.write_text(
        json.dumps(episode, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if args.set_latest:
        (args.radio_dir / "episodes" / "latest.json").write_text(
            json.dumps(episode, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    if len(episode.get("stories", [])) != 3:
        failures.append("episode does not contain exactly three stories")
    missing = [
        str(index)
        for index, story in enumerate(episode.get("stories", []), 1)
        if not story.get("image")
    ]
    if missing:
        failures.append("missing verified cover image for story " + ", ".join(missing))
    if failures:
        raise RuntimeError("; ".join(failures))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
