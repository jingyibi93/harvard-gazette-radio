#!/usr/bin/env python3
"""Mirror the public radio data from Supabase into Railway's local cache."""

from __future__ import annotations

import json
import os
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
DEFAULT_BASE = (
    "https://wnifqbhtsbqafbkrvgxb.supabase.co/storage/v1/object/public/"
    "harvard-radio"
)
DATA_BASE = os.environ.get("HARVARD_RADIO_SOURCE", DEFAULT_BASE).rstrip("/")
ALLOWED_PREFIXES = ("episodes/", "audio/", "images/")


def fetch(path: str) -> bytes:
    encoded = urllib.parse.quote(path, safe="/")
    request = urllib.request.Request(
        f"{DATA_BASE}/{encoded}",
        headers={"User-Agent": "HarvardGazetteRadio-Railway/1.0"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def write_atomic(destination: Path, content: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
        handle.write(content)
        temporary = Path(handle.name)
    temporary.chmod(0o644)
    temporary.replace(destination)


def main() -> int:
    manifest = json.loads(fetch("manifest.json"))
    files = [
        str(path)
        for path in manifest.get("files", [])
        if str(path).startswith(ALLOWED_PREFIXES)
    ]
    if not files:
        raise RuntimeError("The public radio manifest is empty.")

    for relative in files:
        write_atomic(SITE / relative, fetch(relative))

    expected = set(files)
    for prefix in ("episodes", "audio", "images"):
        directory = SITE / prefix
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if path.is_file() and path.relative_to(SITE).as_posix() not in expected:
                path.unlink()

    print(f"Railway cache synchronized: {len(files)} files.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
