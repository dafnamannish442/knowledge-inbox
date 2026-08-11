#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BANNED_ROOTS = {"data", ".venv", "gpt-link"}
BANNED_SUFFIXES = {
    ".cer",
    ".db",
    ".key",
    ".mov",
    ".mp4",
    ".p12",
    ".pem",
    ".pfx",
    ".sqlite",
    ".zip",
}
MAX_FILE_BYTES = 10 * 1024 * 1024
TEXT_PATTERNS = {
    "macOS user path": re.compile("/" + r"Users/[^/\s]+"),
    "external volume path": re.compile("/" + r"Volumes/[^/\s]+"),
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "OpenAI-style secret": re.compile(r"\b(?:sk|ocx)_[A-Za-z0-9_-]{20,}\b"),
    "GitHub token": re.compile(r"\bgh[opusr]_[A-Za-z0-9_]{20,}\b"),
    "AWS access key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "Google API key": re.compile(r"\bAIza[A-Za-z0-9_-]{30,}\b"),
    "non-empty YAML API key": re.compile(r"(?im)^\s*api_key:\s*[^\s\"']+\s*$"),
}


def public_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode == 0 and result.stdout:
        return [ROOT / value.decode() for value in result.stdout.split(b"\0") if value]
    return [path for path in ROOT.rglob("*") if path.is_file() and ".git" not in path.parts]


def main() -> int:
    failures: list[str] = []
    paths = public_files()
    tracked_roots = {path.relative_to(ROOT).parts[0] for path in paths}
    for name in sorted(BANNED_ROOTS & tracked_roots):
        failures.append(f"banned root path: {name}")

    for path in sorted(paths):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        size = path.stat().st_size
        if path.suffix.lower() in BANNED_SUFFIXES:
            failures.append(f"banned file type: {relative}")
            continue
        if size > MAX_FILE_BYTES:
            failures.append(f"file exceeds 10 MiB: {relative}")
            continue
        try:
            content = path.read_text("utf-8")
        except UnicodeDecodeError:
            continue
        for label, pattern in TEXT_PATTERNS.items():
            if pattern.search(content):
                failures.append(f"{label}: {relative}")

    if failures:
        print("Release check failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print("Release check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
