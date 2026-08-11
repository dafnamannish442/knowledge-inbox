#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import httpx


def classify_input(value: str) -> tuple[str, str | Path]:
    path = Path(value).expanduser()
    if path.is_file():
        return "file", path
    if value.startswith(("http://", "https://")):
        return "url", value
    return "text", value


def main() -> None:
    parser = argparse.ArgumentParser(description="摄入链接、文件或文字并等待 Obsidian 卡片")
    parser.add_argument("input", help="URL、本地文件路径或文字")
    parser.add_argument("--title", help="自定义标题")
    parser.add_argument("--source-url", help="上传文件的原始来源 URL")
    parser.add_argument(
        "--api",
        default=os.getenv("KNOWLEDGE_API_URL", "http://127.0.0.1:8787"),
        help="知识摄入服务地址",
    )
    parser.add_argument("--timeout", type=int, default=600, help="最长等待秒数")
    args = parser.parse_args()

    kind, value = classify_input(args.input)
    with httpx.Client(base_url=args.api, timeout=60, trust_env=True) as client:
        if kind == "file":
            path = Path(value)
            data = {"title": args.title or path.stem}
            if args.source_url:
                data["source_url"] = args.source_url
            with path.open("rb") as source:
                response = client.post(
                    "/api/upload",
                    data=data,
                    files={"file": (path.name, source)},
                )
        else:
            response = client.post(
                "/api/ingest",
                json={kind: value, "title": args.title},
            )
        response.raise_for_status()
        job = response.json()
        print(f"任务已提交：{job['id']}")

        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            job = client.get(f"/api/jobs/{job['id']}").raise_for_status().json()
            if job["status"] == "succeeded":
                print(job["note_path"])
                return
            if job["status"] == "failed":
                print(job["error"], file=sys.stderr)
                raise SystemExit(1)
            time.sleep(1)
    raise SystemExit(f"等待任务超时（{args.timeout} 秒）")


if __name__ == "__main__":
    main()
