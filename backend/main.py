from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from backend.adapters import build_registry
from backend.api.routes import router
from backend.config import get_config
from backend.processors.ai import AIProcessor
from backend.processors.linker import KnowledgeLinker
from backend.processors.pipeline import ContentPipeline
from backend.storage import Database, ObsidianWriter
from backend.worker import IngestionWorker


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = get_config()
    database = Database(config.database_path)
    database.initialize()
    pipeline = ContentPipeline(
        build_registry(config),
        database,
        ObsidianWriter(config),
        AIProcessor(config.ai),
        KnowledgeLinker(config),
    )
    worker = IngestionWorker(database, pipeline)
    app.state.config = config
    app.state.database = database
    app.state.worker = worker
    await worker.start()
    yield
    await worker.stop()


app = FastAPI(
    title="Knowledge Ingestion Service",
    version="0.3.0",
    lifespan=lifespan,
)
app.include_router(router)


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    return FileResponse(Path(__file__).parent.parent / "frontend" / "index.html")
