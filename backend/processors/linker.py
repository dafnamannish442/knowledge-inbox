from __future__ import annotations

import json
import re
import shlex
import subprocess
from pathlib import Path

from backend.config import AppConfig
from backend.models import ContentItem


class KnowledgeLinker:
    def __init__(self, config: AppConfig):
        self.config = config

    def find_related(self, item: ContentItem, limit: int = 5) -> list[str]:
        query = " ".join([item.title, *item.keywords[:6], *item.tags[:4]]).strip()
        if query:
            qmd_results = self._query_qmd(query, limit)
            if qmd_results:
                return qmd_results
        return self._lexical_search(item, limit)

    def _query_qmd(self, query: str, limit: int) -> list[str]:
        command = [*shlex.split(self.config.qmd_command), "query", query, "--json", "--limit", str(limit)]
        if self.config.qmd_collection:
            command.extend(["--collection", self.config.qmd_collection])
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=20, check=True)
            payload = json.loads(result.stdout)
        except (FileNotFoundError, subprocess.SubprocessError, json.JSONDecodeError):
            return []

        rows = payload if isinstance(payload, list) else payload.get("results", [])
        notes: list[str] = []
        for row in rows:
            path = row.get("path") or row.get("file") if isinstance(row, dict) else None
            if path:
                notes.append(Path(path).stem)
        return list(dict.fromkeys(notes))[:limit]

    def _lexical_search(self, item: ContentItem, limit: int) -> list[str]:
        needles = {
            token.lower()
            for token in [*item.tags, *item.keywords, *re.findall(r"\w{2,}", item.title)]
            if token
        }
        if not needles or not self.config.vault_dir or not self.config.vault_dir.exists():
            return []
        scored: list[tuple[int, str]] = []
        paths = sorted(
            self.config.vault_dir.rglob("*.md"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )[:1000]
        for path in paths:
            try:
                haystack = f"{path.stem}\n{path.read_text('utf-8', errors='ignore')[:8000]}".lower()
            except OSError:
                continue
            score = sum(1 for token in needles if token in haystack)
            if score:
                scored.append((score, path.stem))
        scored.sort(reverse=True)
        return [name for _, name in scored[:limit]]
