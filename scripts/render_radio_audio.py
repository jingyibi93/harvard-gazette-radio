#!/usr/bin/env python3
"""Render neural narration with a user-provided morning-news intro and outro."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


VOICES = {
    "zh": ("zh-CN-XiaoxiaoNeural", "+2%", "-2Hz"),
    "en": ("en-US-AriaNeural", "-2%", "-1Hz"),
}

DEFAULT_MUSIC = Path(__file__).resolve().parent.parent / "assets/music/window-on-the-world.mp3"
VOICE_DELAY = 2.5


def command(name: str, env_name: str | None = None) -> str:
    candidate = os.environ.get(env_name, "") if env_name else ""
    path = candidate or shutil.which(name)
    if not path:
        hint = f" or set {env_name}" if env_name else ""
        raise RuntimeError(f"Missing required command: {name}{hint}")
    return path


def duration(ffprobe: str, path: Path) -> float:
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def shift_srt(source: Path, destination: Path, offset: float) -> None:
    stamp = re.compile(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})")

    def shift(match: re.Match[str]) -> str:
        hours, minutes, seconds, milliseconds = map(int, match.groups())
        total = hours * 3600 + minutes * 60 + seconds + milliseconds / 1000 + offset
        whole = int(total)
        millis = round((total - whole) * 1000)
        if millis == 1000:
            whole += 1
            millis = 0
        return f"{whole // 3600:02d}:{whole % 3600 // 60:02d}:{whole % 60:02d},{millis:03d}"

    destination.write_text(stamp.sub(shift, source.read_text(encoding="utf-8")), encoding="utf-8")


def render(
    language: str,
    text: Path,
    output: Path,
    music_path: Path,
    edge_tts: str,
    ffmpeg: str,
    ffprobe: str,
) -> None:
    voice, rate, pitch = VOICES[language]
    with tempfile.TemporaryDirectory(prefix="harvard-radio-") as temp_dir:
        narration = Path(temp_dir) / f"{language}-voice.mp3"
        subtitles = Path(temp_dir) / f"{language}-voice.srt"
        subprocess.run(
            [
                edge_tts,
                "--voice",
                voice,
                f"--rate={rate}",
                f"--pitch={pitch}",
                "--file",
                str(text),
                "--write-media",
                str(narration),
                "--write-subtitles",
                str(subtitles),
            ],
            check=True,
        )
        shift_srt(subtitles, output.with_suffix(".srt"), VOICE_DELAY)
        voice_seconds = duration(ffprobe, narration)
        outro_start_ms = round((VOICE_DELAY + voice_seconds - 3.0) * 1000)
        filter_graph = (
            "[1:a]atrim=start=0:end=9,asetpts=PTS-STARTPTS,"
            "volume=0.20,afade=t=in:st=0:d=0.8,afade=t=out:st=6:d=3[intro];"
            "[1:a]atrim=start=9:end=20,asetpts=PTS-STARTPTS,"
            f"volume=0.22,afade=t=in:st=0:d=2,afade=t=out:st=8.5:d=2.5,"
            f"adelay={outro_start_ms}:all=1[outro];"
            f"[0:a]adelay={round(VOICE_DELAY * 1000)}:all=1,volume=1.0[voice];"
            "[voice][intro][outro]amix=inputs=3:duration=longest:normalize=0,"
            "alimiter=limit=0.92[out]"
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(narration),
                "-i",
                str(music_path),
                "-filter_complex",
                filter_graph,
                "-map",
                "[out]",
                "-c:a",
                "aac",
                "-b:a",
                "112k",
                str(output),
            ],
            check=True,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("radio_dir", type=Path)
    parser.add_argument("--episode-id", default="latest")
    parser.add_argument(
        "--music",
        type=Path,
        default=DEFAULT_MUSIC,
        help="MP3 used only for the opening and closing news themes.",
    )
    args = parser.parse_args()
    if not args.music.is_file():
        parser.error(f"Music file not found: {args.music}")
    audio_dir = args.radio_dir / "audio"
    edge_tts = command("edge-tts", "EDGE_TTS_BIN")
    ffmpeg = command("ffmpeg")
    ffprobe = command("ffprobe")
    for language in ("zh", "en"):
        render(
            language,
            audio_dir / f"{args.episode_id}-{language}.txt",
            audio_dir / f"{args.episode_id}-{language}.m4a",
            args.music,
            edge_tts,
            ffmpeg,
            ffprobe,
        )
        print(f"Rendered {audio_dir / f'{args.episode_id}-{language}.m4a'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
