from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class AIConfig(BaseModel):
    enabled: bool = False
    base_url: str = "http://127.0.0.1:11434/v1"
    api_key: str = ""
    model: str = "qwen2.5:7b"
    vision_model: str | None = None
    timeout_seconds: int = 180


class AppConfig(BaseModel):
    data_dir: Path = Field(default_factory=lambda: Path(os.getenv("KNOWLEDGE_DATA_DIR", "./data")))
    vault_dir: Path = Field(default_factory=lambda: Path(os.getenv("OBSIDIAN_VAULT_DIR", "./data/ObsidianVault")))
    inbox_folder: str = "Knowledge Inbox"
    database_path: Path = Path("./data/knowledge.sqlite")
    ai: AIConfig = Field(default_factory=AIConfig)
    qmd_command: str = "qmd"
    qmd_collection: str | None = None
    max_download_mb: int = 500
    download_remote_media: bool = True
    delete_video_after_ingest: bool = False
    wechat_video_downloader_url: str | None = "http://127.0.0.1:2022"
    wechat_video_download_timeout_seconds: int = 300
    playwright_user_data_dir: Path | None = None
    telegram_webhook_secret: str | None = None

    def prepare(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.vault_dir.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_config() -> AppConfig:
    env_path = os.getenv("KNOWLEDGE_CONFIG")
    if env_path:
        config_path = Path(env_path).resolve()
    else:
        config_path = (Path(__file__).resolve().parents[1] / "config.yaml").resolve()
    raw = yaml.safe_load(config_path.read_text("utf-8")) if config_path.exists() else {}
    raw = raw or {}

    if value := os.getenv("KNOWLEDGE_DATA_DIR"):
        raw["data_dir"] = value
    if value := os.getenv("OBSIDIAN_VAULT_DIR"):
        raw["vault_dir"] = value
    if value := os.getenv("KNOWLEDGE_OPENAI_BASE_URL") or os.getenv("OPENAI_BASE_URL"):
        raw.setdefault("ai", {})["base_url"] = value
    if value := os.getenv("OPENAI_API_KEY"):
        raw.setdefault("ai", {})["api_key"] = value
    if value := os.getenv("OPENAI_MODEL"):
        raw.setdefault("ai", {})["model"] = value
    if value := os.getenv("OPENAI_VISION_MODEL"):
        raw.setdefault("ai", {})["vision_model"] = value
    if os.getenv("AI_ENABLED"):
        raw.setdefault("ai", {})["enabled"] = os.environ["AI_ENABLED"].lower() == "true"

    config = AppConfig.model_validate(raw)
    if not config.data_dir.is_absolute():
        config.data_dir = (config_path.parent / config.data_dir).resolve()
    if not config.vault_dir.is_absolute():
        config.vault_dir = (config_path.parent / config.vault_dir).resolve()
    if not config.database_path.is_absolute():
        config.database_path = (config.data_dir / config.database_path.name).resolve()
    config.prepare()
    return config
