from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from backend.models import ContentItem, Job, JobStatus


class Database:
    def __init__(self, path: Path):
        self.path = path

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    input_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    item_id TEXT,
                    note_path TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS items (
                    id TEXT PRIMARY KEY,
                    source_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    source_url TEXT,
                    note_path TEXT NOT NULL,
                    data TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_jobs_updated_at ON jobs(updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_items_created_at ON items(created_at DESC);
                """
            )

    def save_job(self, job: Job) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO jobs
                (id, status, input_type, payload, item_id, note_path, error, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status=excluded.status,
                    payload=excluded.payload,
                    item_id=excluded.item_id,
                    note_path=excluded.note_path,
                    error=excluded.error,
                    updated_at=excluded.updated_at
                """,
                (
                    job.id,
                    job.status.value,
                    job.input_type,
                    json.dumps(job.payload, ensure_ascii=False),
                    job.item_id,
                    job.note_path,
                    job.error,
                    job.created_at.isoformat(),
                    job.updated_at.isoformat(),
                ),
            )

    def update_job(
        self,
        job_id: str,
        status: JobStatus,
        *,
        item_id: str | None = None,
        note_path: str | None = None,
        error: str | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET status=?, item_id=COALESCE(?, item_id), note_path=COALESCE(?, note_path),
                    error=?, updated_at=?
                WHERE id=?
                """,
                (
                    status.value,
                    item_id,
                    note_path,
                    error,
                    datetime.now(timezone.utc).isoformat(),
                    job_id,
                ),
            )

    def get_job(self, job_id: str) -> Job | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        return self._job_from_row(row) if row else None

    def list_jobs(self, limit: int = 50) -> list[Job]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._job_from_row(row) for row in rows]

    def recoverable_job_ids(self) -> list[str]:
        with self._connect() as connection:
            connection.execute(
                "UPDATE jobs SET status=? WHERE status=?",
                (JobStatus.QUEUED.value, JobStatus.RUNNING.value),
            )
            rows = connection.execute(
                "SELECT id FROM jobs WHERE status=? ORDER BY created_at",
                (JobStatus.QUEUED.value,),
            ).fetchall()
        return [row["id"] for row in rows]

    def save_item(self, item: ContentItem, note_path: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO items
                (id, source_type, title, source_url, note_path, data, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    item.id,
                    item.source_type,
                    item.title,
                    item.source_url,
                    note_path,
                    item.model_dump_json(),
                    item.created_at.isoformat(),
                ),
            )

    def list_items(self, limit: int = 50) -> list[dict[str, str | None]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, source_type, title, source_url, note_path, created_at
                FROM items ORDER BY created_at DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=20)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=20000")
        return connection

    @staticmethod
    def _job_from_row(row: sqlite3.Row) -> Job:
        return Job(
            id=row["id"],
            status=row["status"],
            input_type=row["input_type"],
            payload=json.loads(row["payload"]),
            item_id=row["item_id"],
            note_path=row["note_path"],
            error=row["error"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
