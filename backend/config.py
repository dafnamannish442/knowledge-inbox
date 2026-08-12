from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from tempfile import NamedTemporaryFile

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
    vault_dir: Path | None = None
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
        if self.vault_dir:
            self.vault_dir.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def storage_config_path(self) -> Path:
        return self.data_dir / "storage.yaml"

    @property
    def storage_configured(self) -> bool:
        return self.vault_dir is not None


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
    data_dir = Path(raw.get("data_dir", "./data")).expanduser()
    if not data_dir.is_absolute():
        data_dir = (config_path.parent / data_dir).resolve()
    storage_path = data_dir / "storage.yaml"
    if storage_path.exists():
        stored = yaml.safe_load(storage_path.read_text("utf-8")) or {}
        for key in ("vault_dir", "inbox_folder"):
            if key in stored:
                raw[key] = stored[key]
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
    if config.vault_dir and not config.vault_dir.is_absolute():
        config.vault_dir = (config_path.parent / config.vault_dir).resolve()
    if not config.database_path.is_absolute():
        config.database_path = (config.data_dir / config.database_path.name).resolve()
    config.prepare()
    return config


def save_storage_settings(config: AppConfig, vault_dir: str, inbox_folder: str) -> None:
    if os.getenv("OBSIDIAN_VAULT_DIR"):
        raise ValueError("知识库路径由 OBSIDIAN_VAULT_DIR 管理，不能在网页中修改")

    vault = Path(vault_dir).expanduser()
    if not vault.is_absolute():
        raise ValueError("知识库路径必须是绝对路径")
    if not vault.exists() or not vault.is_dir():
        raise ValueError("知识库文件夹不存在")
    vault = vault.resolve()

    folder = Path(inbox_folder.strip())
    if not inbox_folder.strip() or folder.is_absolute() or ".." in folder.parts:
        raise ValueError("卡片子目录必须是知识库内的相对路径")
    target = (vault / folder).resolve()
    if not target.is_relative_to(vault):
        raise ValueError("卡片子目录不能超出知识库")

    try:
        target.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(prefix=".knowledge-ingestion-", dir=target):
            pass
    except OSError as error:
        raise ValueError(f"知识库文件夹不可写：{error}") from error

    config.data_dir.mkdir(parents=True, exist_ok=True)
    payload = {"vault_dir": str(vault), "inbox_folder": folder.as_posix()}
    with NamedTemporaryFile(
        "w", encoding="utf-8", dir=config.data_dir, delete=False
    ) as temporary:
        yaml.safe_dump(payload, temporary, allow_unicode=True, sort_keys=False)
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, config.storage_config_path)
    config.vault_dir = vault
    config.inbox_folder = folder.as_posix()
