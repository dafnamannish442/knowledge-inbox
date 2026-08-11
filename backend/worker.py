from __future__ import annotations

import asyncio
import logging

from backend.models import Job, JobStatus
from backend.processors import ContentPipeline
from backend.storage import Database

logger = logging.getLogger(__name__)


class IngestionWorker:
    def __init__(self, database: Database, pipeline: ContentPipeline):
        self.database = database
        self.pipeline = pipeline
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        for job_id in await asyncio.to_thread(self.database.recoverable_job_ids):
            await self.queue.put(job_id)
        self._task = asyncio.create_task(self._run(), name="knowledge-ingestion-worker")

    async def stop(self) -> None:
        if not self._task:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass

    async def submit(self, job: Job) -> None:
        await asyncio.to_thread(self.database.save_job, job)
        await self.queue.put(job.id)

    async def _run(self) -> None:
        while True:
            job_id = await self.queue.get()
            try:
                await self._process(job_id)
            finally:
                self.queue.task_done()

    async def _process(self, job_id: str) -> None:
        job = await asyncio.to_thread(self.database.get_job, job_id)
        if not job:
            return
        await asyncio.to_thread(self.database.update_job, job.id, JobStatus.RUNNING)
        try:
            item, note_path = await self.pipeline.process(job)
        except Exception as error:
            logger.exception("Ingestion job %s failed", job.id)
            await asyncio.to_thread(
                self.database.update_job,
                job.id,
                JobStatus.FAILED,
                error=f"{type(error).__name__}: {error}",
            )
            return
        await asyncio.to_thread(
            self.database.update_job,
            job.id,
            JobStatus.SUCCEEDED,
            item_id=item.id,
            note_path=str(note_path),
        )
