#!/usr/bin/env python3
"""Securely migrate seed data and configure GitHub Actions secrets."""

from __future__ import annotations

import getpass
import os
import subprocess
import sys
from pathlib import Path

import daily_brief


ROOT = Path(__file__).resolve().parent.parent


def required_local(env_name: str, service: str, label: str, hidden: bool) -> str:
    value = daily_brief.setting(env_name, service)
    if value:
        return value
    prompt = f"{label}: "
    return getpass.getpass(prompt) if hidden else input(prompt).strip()


def set_secret(name: str, value: str) -> None:
    subprocess.run(
        ["gh", "secret", "set", name],
        input=value + "\n",
        text=True,
        cwd=ROOT,
        check=True,
    )


def main() -> int:
    print("密钥只会发送到 GitHub Secrets，不会显示或写入项目文件。")
    supabase_url = input("Supabase Project URL: ").strip().rstrip("/")
    supabase_key = getpass.getpass("Supabase service_role key: ").strip()
    if not supabase_url.startswith("https://") or not supabase_key:
        raise RuntimeError("Supabase URL 或 service_role key 无效。")

    values = {
        "MAIL163_USER": required_local(
            "MAIL163_USER", "harvard-daily-brief-mail163-user", "163 邮箱地址", False
        ),
        "MAIL163_AUTH_CODE": required_local(
            "MAIL163_AUTH_CODE", "harvard-daily-brief-mail163-auth", "163 授权密码", True
        ),
        "AGNES_API_KEY": required_local(
            "AGNES_API_KEY", "harvard-daily-brief-agnes-key", "Agnes API Key", True
        ),
        "SUPABASE_URL": supabase_url,
        "SUPABASE_SERVICE_ROLE_KEY": supabase_key,
    }
    if not all(values.values()):
        raise RuntimeError("缺少必要的云端密钥。")

    environment = os.environ.copy()
    environment.update(
        {
            "SUPABASE_URL": supabase_url,
            "SUPABASE_SERVICE_ROLE_KEY": supabase_key,
        }
    )
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "supabase_storage.py"), "upload"],
        cwd=ROOT,
        env=environment,
        check=True,
    )
    for name, value in values.items():
        set_secret(name, value)
        print(f"已设置 {name}")
    print("Supabase 初始节目迁移与 GitHub Secrets 配置完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
