#!/usr/bin/env python3
"""Publish a generated Markdown brief as a Harvard Radio web episode."""

from __future__ import annotations

import argparse
import datetime as dt
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
        r"(?:我是(?:您的|你们的)?(?:AI|人工智能)?(?:主持人|主播|助手)[^。！？.!?]*[。！？.!?]?)",
        "",
        text,
    )
    text = re.sub(
        r"(?:I(?:['’]m| am) (?:your |the )?(?:AI |artificial intelligence )?(?:host|presenter|assistant)[^.!?]*[.!?]?)",
        "",
        text,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_stories(markdown: str) -> list[tuple[str, str, str, str]]:
    lines = markdown.splitlines()
    stories: list[tuple[str, str, str, str]] = []
    labeled_source = re.compile(
        r"(?:\*\*)?(?:来源|Source)\s*[：:]\s*(?:\*\*)?\s*"
        r"\[([^\]]+)\]\((https?://[^)]+)\)",
        re.IGNORECASE,
    )
    source_link = re.compile(
        r"\[([^\]]*(?:来源|Source)[^\]]*)\]\((https?://[^)]+)\)",
        re.IGNORECASE,
    )
    for index, line in enumerate(lines):
        source = labeled_source.search(line) or source_link.search(line)
        if not source:
            continue
        title = ""
        english_title = ""
        for candidate in reversed(lines[max(0, index - 8):index]):
            english = re.match(
                r"^(?:\*\*)?(?:English title|英文标题)\s*[：:]\s*(?:\*\*)?\s*(.+?)\s*$",
                candidate,
                re.IGNORECASE,
            )
            if english and not english_title:
                english_title = english.group(1).strip().strip("*").strip()
            heading = re.match(r"^###\s+(?:\d+\.\s+)?(.+?)\s*$", candidate)
            bold = re.match(
                r"^\*\*(?!(?:为何重要|来源|Why it matters|Source))(.+?)\*\*\s*$",
                candidate,
                re.IGNORECASE,
            )
            match = heading or bold
            if match:
                title = match.group(1).strip()
                break
        if title:
            stories.append((title, english_title, source.group(1), source.group(2)))
    return stories[:3]


def public_url(url: str) -> str:
    """Remove newsletter recipient tracking before a URL reaches the public site."""
    parsed = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def title_from_url(url: str) -> str:
    path = urllib.parse.urlsplit(url).path.strip("/")
    slug = path.split("/")[-1]
    words = [word for word in re.split(r"[-_]+", slug) if word]
    minor = {"a", "an", "and", "at", "for", "from", "in", "of", "on", "or", "the", "to", "with", "without"}
    titled = [
        word if index and word in minor else word.capitalize()
        for index, word in enumerate(words)
    ]
    return " ".join(titled)


def compact_zh_topic(title: str) -> str:
    title = re.sub(r"\s+", "", title).strip("。！？.!?")
    if "疫苗" in title and ("癌症" in title or "疟疾" in title):
        return "癌症与疟疾疫苗"
    if "联邦党" in title:
        return "联邦党协会崛起"
    if "新药" in title or "鲨鱼坦克" in title:
        return "新药创业路演"
    if "公园" in title and "灵感" in title:
        return "公园里的创意灵感"
    for delimiter in ("：", ":", "，", "、"):
        if delimiter in title:
            pieces = [piece for piece in title.split(delimiter) if piece]
            title = min(pieces, key=len) if pieces else title
            break
    return title[:12]


def compact_en_topic(title: str) -> str:
    normalized = title.strip()
    lower = normalized.casefold()
    if "vaccine" in lower and ("cancer" in lower or "malaria" in lower):
        return "Cancer and malaria vaccines"
    if "federalist society" in lower:
        return "Federalist Society rise"
    if "shark tank" in lower or "guppy tank" in lower:
        return "new-drug startup pitch"
    if "park" in lower and "inspiration" in lower:
        return "park-born inspiration"
    normalized = re.sub(r"^(?:how|why|what|when)\s+", "", normalized, flags=re.IGNORECASE)
    return normalized[:42].rstrip(" ,;:")


def program_title_from_stories(stories: list[dict[str, str]]) -> dict[str, str]:
    zh_topics = [compact_zh_topic(story["zh"]) for story in stories]
    en_topics = [compact_en_topic(story["en"]) for story in stories]
    return {
        "zh": "、".join(zh_topics[:-1]) + "与" + zh_topics[-1] if len(zh_topics) > 1 else zh_topics[0],
        "en": ", ".join(en_topics[:-1]) + ", and " + en_topics[-1] if len(en_topics) > 1 else en_topics[0],
    }


STOPWORDS_EN = {
    "about",
    "after",
    "again",
    "could",
    "from",
    "have",
    "into",
    "more",
    "that",
    "their",
    "them",
    "then",
    "there",
    "these",
    "think",
    "this",
    "those",
    "what",
    "when",
    "where",
    "which",
    "while",
    "with",
    "without",
    "would",
}

STOPWORDS_ZH = {
    "一个",
    "一种",
    "以及",
    "今日",
    "哈佛",
    "如何",
    "我们",
    "故事",
    "新闻",
    "研究",
    "为何",
    "背后",
}


def story_keywords(title: str, english_title: str) -> tuple[list[str], list[str]]:
    zh_chunks = [
        chunk
        for chunk in re.split(r"[，、：:；;“”‘’《》\s,.!?()\[\]{}-]+", title)
        if len(chunk) >= 2 and chunk not in STOPWORDS_ZH
    ]
    zh_pairs = [
        title[index : index + 2]
        for index in range(max(0, len(title) - 1))
        if re.match(r"[\u4e00-\u9fff]{2}", title[index : index + 2])
        and title[index : index + 2] not in STOPWORDS_ZH
    ]
    english_words = [
        word.casefold()
        for word in re.findall(r"[A-Za-z][A-Za-z'’-]{2,}", english_title)
        if word.casefold().strip("'’") not in STOPWORDS_EN
    ]
    return list(dict.fromkeys(zh_chunks + zh_pairs)), list(dict.fromkeys(english_words))


def validate_broadcast_alignment(
    stories: list[dict[str, str]],
    zh_script: str,
    en_script: str,
) -> None:
    zh_plain = re.sub(r"\s+", "", zh_script)
    en_plain = en_script.casefold()
    for index, story in enumerate(stories, 1):
        zh_title = story["zh"]
        en_title = story["en"]
        zh_keywords, en_keywords = story_keywords(zh_title, en_title)
        zh_hits = [keyword for keyword in zh_keywords if keyword in zh_plain]
        en_hits = [keyword for keyword in en_keywords if keyword in en_plain]
        zh_title_hit = re.sub(r"\s+", "", zh_title) in zh_plain
        en_title_hit = en_title.casefold() in en_plain
        if not zh_title_hit and len(zh_hits) < 2:
            raise ValueError(
                f"Broadcast does not appear to cover story {index}: {zh_title}"
            )
        if not en_title_hit and not en_hits:
            raise ValueError(
                f"English broadcast does not appear to cover story {index}: {en_title}"
            )


DRIFT_TERMS_ZH = ("公园", "发明家", "灵感")
DRIFT_TERMS_EN = ("park", "parks", "inventor", "inventors", "inspiration")


def closing_paragraph(text: str) -> str:
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n{2,}", text.strip()) if paragraph.strip()]
    return paragraphs[-1] if paragraphs else ""


def contains_unselected_drift(text: str, stories: list[dict[str, str]], terms: tuple[str, ...]) -> bool:
    selected = " ".join(story["zh"] + " " + story["en"] for story in stories).casefold()
    lower_text = text.casefold()
    return any(term.casefold() in lower_text and term.casefold() not in selected for term in terms)


def replace_closing(text: str, replacement: str) -> str:
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n{2,}", text.strip()) if paragraph.strip()]
    if not paragraphs:
        return replacement
    paragraphs[-1] = replacement
    return "\n\n".join(paragraphs)


def clean_broadcast_closing(
    stories: list[dict[str, str]],
    zh_script: str,
    en_script: str,
) -> tuple[str, str]:
    zh_closing = closing_paragraph(zh_script)
    en_closing = closing_paragraph(en_script)
    if contains_unselected_drift(zh_closing, stories, DRIFT_TERMS_ZH):
        zh_script = replace_closing(
            zh_script,
            "以上就是今天早间新闻的全部内容。感谢收听，祝您拥有清醒、充实的一天。早安！",
        )
    if contains_unselected_drift(en_closing, stories, DRIFT_TERMS_EN):
        en_script = replace_closing(
            en_script,
            "That concludes this morning’s briefing. Thank you for listening, and have a thoughtful day.",
        )
    return zh_script, en_script


def edition_date(episode_id: str, fallback: str) -> str:
    try:
        value = dt.date.fromisoformat(episode_id)
        return f"{value.year}年{value.month}月{value.day}日"
    except ValueError:
        return fallback.strip()


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
    english_program_title_match = re.search(
        r"(?mi)^\*\*English program title:\*\*\s*(.+?)\s*$",
        markdown,
    )
    date_match = re.search(
        r"\*\*(?:日期|Date)\s*[：:]\*\*\s*(.+)",
        markdown,
        re.IGNORECASE,
    )
    if not date_match and title_match:
        date_match = re.search(r"(20\d{2}年\d{1,2}月\d{1,2}日)", title_match.group(1))
    if not date_match:
        date_match = re.search(r"(20\d{2}[-/.]\d{1,2}[-/.]\d{1,2})", markdown)
    story_matches = extract_stories(markdown)
    if not title_match or not english_program_title_match or not date_match or not story_matches:
        raise ValueError(
            "The brief does not contain the expected paired program titles, date, and stories."
        )
    if any(not english_title for _, english_title, _, _ in story_matches):
        story_matches = [
            (title, english_title or title_from_url(url), source, url)
            for title, english_title, source, url in story_matches
        ]

    stories = [
        {
            "zh": title,
            "en": english_title,
            "source": source,
            "url": public_url(url),
        }
        for title, english_title, source, url in story_matches[:3]
    ]
    zh = spoken(section(markdown, "中文电台 Broadcast", "English Radio Broadcast"))
    en = spoken(section(markdown, "English Radio Broadcast"))
    zh, en = clean_broadcast_closing(stories, zh, en)
    validate_broadcast_alignment(stories, zh, en)
    episode_dir = radio_dir / "episodes"
    audio_dir = radio_dir / "audio"
    episode_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)
    (audio_dir / f"{episode_id}-zh.txt").write_text(zh + "\n", encoding="utf-8")
    (audio_dir / f"{episode_id}-en.txt").write_text(en + "\n", encoding="utf-8")
    display_date = edition_date(episode_id, date_match.group(1))
    audio_version = re.sub(r"\D", "", episode_id) or re.sub(r"\D", "", display_date) or "latest"
    payload = {
        "date": display_date,
        "title": program_title_from_stories(stories),
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
        "datePolicy": "next-beijing-morning",
        "scriptDatePolicy": "next-beijing-morning-spoken-date",
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
