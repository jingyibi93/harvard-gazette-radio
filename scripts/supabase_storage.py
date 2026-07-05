#!/usr/bin/env python3
"""Synchronize public Harvard Radio data with a Supabase Storage bucket."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
BUCKET = os.environ.get("SUPABASE_BUCKET", "harvard-radio")
PREFIXES = ("episodes", "audio", "images")


def settings(require_key: bool) -> tuple[str, str]:
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not base:
        raise RuntimeError("SUPABASE_URL is required.")
    if require_key and not key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is required.")
    return base, key


def api(
    url: str,
    *,
    key: str = "",
    method: str = "GET",
    data: bytes | None = None,
    content_type: str = "application/json",
    extra_headers: dict[str, str] | None = None,
) -> bytes:
    headers = {"Content-Type": content_type}
    headers.update(extra_headers or {})
    if key:
        headers["apikey"] = key
        if not key.startswith("sb_secret_"):
            headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read(500).decode(errors="replace")
        raise RuntimeError(f"Supabase returned HTTP {exc.code}: {detail}") from exc


def public_url(base: str, path: str) -> str:
    encoded = urllib.parse.quote(path, safe="/")
    return f"{base}/storage/v1/object/public/{BUCKET}/{encoded}"


def ensure_bucket(base: str, key: str) -> None:
    body = json.dumps(
        {
            "id": BUCKET,
            "name": BUCKET,
            "public": True,
            "file_size_limit": 50 * 1024 * 1024,
        }
    ).encode()
    try:
        api(f"{base}/storage/v1/bucket", key=key, method="POST", data=body)
    except RuntimeError as exc:
        if "already exists" not in str(exc).casefold():
            raise


def local_files() -> list[str]:
    return sorted(
        path.relative_to(SITE).as_posix()
        for prefix in PREFIXES
        for path in (SITE / prefix).rglob("*")
        if path.is_file()
    )


def remote_manifest(base: str) -> list[str]:
    try:
        raw = api(public_url(base, "manifest.json"))
    except RuntimeError as exc:
        if "HTTP 404" in str(exc):
            return []
        raise
    payload = json.loads(raw)
    return [str(path) for path in payload.get("files", [])]


def download() -> None:
    base, _ = settings(False)
    files = remote_manifest(base)
    if not files:
        print("Supabase bucket has no existing manifest; starting from repository seed data.")
        return
    for relative in files:
        if not relative.startswith(PREFIXES):
            continue
        destination = SITE / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(api(public_url(base, relative)))
    print(f"Downloaded {len(files)} public data files from Supabase.")


def upload_file(base: str, key: str, relative: str, content: bytes) -> None:
    content_type = mimetypes.guess_type(relative)[0] or "application/octet-stream"
    encoded = urllib.parse.quote(relative, safe="/")
    api(
        f"{base}/storage/v1/object/{BUCKET}/{encoded}",
        key=key,
        method="POST",
        data=content,
        content_type=content_type,
        extra_headers={"x-upsert": "true", "cache-control": "3600"},
    )


def upload() -> None:
    base, key = settings(True)
    ensure_bucket(base, key)
    previous = set(remote_manifest(base))
    current = set(local_files())
    for relative in sorted(current):
        upload_file(base, key, relative, (SITE / relative).read_bytes())
    obsolete = sorted(previous - current)
    if obsolete:
        body = json.dumps({"prefixes": obsolete}).encode()
        api(
            f"{base}/storage/v1/object/{BUCKET}",
            key=key,
            method="DELETE",
            data=body,
        )
    manifest = json.dumps({"files": sorted(current)}, indent=2).encode()
    upload_file(base, key, "manifest.json", manifest)
    print(f"Uploaded {len(current)} files; removed {len(obsolete)} obsolete files.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("direction", choices=("download", "upload"))
    args = parser.parse_args()
    download() if args.direction == "download" else upload()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
