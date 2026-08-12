#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import time
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import httpx
from macos_wechat_channels import open_channels
from mcp.server.fastmcp import FastMCP

ROOT = Path(__file__).resolve().parents[1]
BACKEND_URL = os.getenv("KNOWLEDGE_API_URL", "http://127.0.0.1:8787")
DOWNLOADER_URL = os.getenv(
    "KNOWLEDGE_WECHAT_DOWNLOADER_URL", "http://127.0.0.1:2022"
)
NETWORKSETUP = "/usr/sbin/networksetup"
NETWORK_SERVICE = os.getenv("KNOWLEDGE_NETWORK_SERVICE", "Wi-Fi")
WECHAT_PROXY_PORT = os.getenv("KNOWLEDGE_WECHAT_PROXY_PORT", "2023")
DOWNLOADER_DIR = Path(
    os.getenv(
        "KNOWLEDGE_WECHAT_DOWNLOADER_DIR",
        str(ROOT / "data" / "tools" / "wx_channels_download"),
    )
).expanduser()

mcp = FastMCP(
    "knowledge-ingestion",
    instructions="Ingest links, local files, videos, screenshots, or text into Obsidian.",
)


def _reachable(url: str) -> bool:
    try:
        return httpx.get(url, timeout=2, trust_env=False).status_code < 500
    except httpx.HTTPError:
        return False


def _start_service(command: list[str], cwd: Path, health_url: str, log_name: str) -> None:
    if _reachable(health_url):
        return
    log_path = ROOT / "data" / log_name
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as log:
        subprocess.Popen(
            command,
            cwd=cwd,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    for _ in range(40):
        if _reachable(health_url):
            return
        time.sleep(0.25)
    raise RuntimeError(f"本地服务启动失败：{health_url}")


def _ensure_backend() -> None:
    _start_service(
        [
            str(ROOT / ".venv" / "bin" / "uvicorn"),
            "backend.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8787",
        ],
        ROOT,
        f"{BACKEND_URL}/api/health",
        "knowledge-backend.log",
    )


def _ensure_downloader() -> None:
    _start_service(
        [str(DOWNLOADER_DIR / "wx_video_download")],
        DOWNLOADER_DIR,
        DOWNLOADER_URL,
        "wechat-downloader.log",
    )


def _channels_available() -> bool:
    try:
        response = httpx.get(
            f"{DOWNLOADER_URL}/api/status",
            timeout=2,
            trust_env=False,
        )
        return bool(response.json()["data"]["channels"]["available"])
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        return False


@dataclass(frozen=True)
class ProxySettings:
    enabled: bool
    server: str
    port: str


def _read_proxy(secure: str) -> ProxySettings:
    result = subprocess.run(
        [NETWORKSETUP, f"-get{secure}webproxy", NETWORK_SERVICE],
        check=True,
        capture_output=True,
        text=True,
    )
    values = {}
    for line in result.stdout.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            values[key.strip()] = value.strip()
    return ProxySettings(
        enabled=values.get("Enabled") == "Yes",
        server=values.get("Server", ""),
        port=values.get("Port", ""),
    )


def _configure_proxy(secure: str, server: str, port: str, enabled: bool) -> None:
    if server and port and port != "0":
        subprocess.run(
            [
                NETWORKSETUP,
                f"-set{secure}webproxy",
                NETWORK_SERVICE,
                server,
                port,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    subprocess.run(
        [
            NETWORKSETUP,
            f"-set{secure}webproxystate",
            NETWORK_SERVICE,
            "on" if enabled else "off",
        ],
        check=True,
        capture_output=True,
        text=True,
    )


@contextmanager
def _temporary_wechat_proxy() -> Iterator[None]:
    previous = {secure: _read_proxy(secure) for secure in ("", "secure")}
    try:
        for secure in ("", "secure"):
            _configure_proxy(secure, "127.0.0.1", WECHAT_PROXY_PORT, True)
        yield
    finally:
        for secure, settings in previous.items():
            _configure_proxy(
                secure,
                settings.server,
                settings.port,
                settings.enabled,
            )


def _reload_wechat_channels() -> None:
    subprocess.run(
        [
            "/usr/bin/pkill",
            "-f",
            "/WeChatAppEx.app/Contents/MacOS/WeChatAppEx --log-level",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    time.sleep(2)
    open_channels()
    # Restart only the Channels extension so the main WeChat login stays intact.
    time.sleep(6)


def _parse_result(stdout: str) -> dict[str, str]:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if len(lines) < 2 or not lines[0].startswith("任务已提交："):
        raise RuntimeError(f"知识摄入脚本返回异常：{stdout[-1000:]}")
    return {
        "status": "succeeded",
        "job_id": lines[0].split("：", 1)[1],
        "note_path": lines[-1],
    }


def _wechat_client_needs_refresh(output: str) -> bool:
    return any(
        marker in output
        for marker in (
            "尚未连接微信客户端",
            "获取详情失败: 请求超时",
        )
    )


@mcp.tool()
def knowledge_list_capabilities() -> dict[str, object]:
    """List supported source and input types for this knowledge ingestion service."""
    _ensure_backend()
    response = httpx.get(
        f"{BACKEND_URL}/api/capabilities",
        timeout=10,
        trust_env=False,
    )
    response.raise_for_status()
    return response.json()


@mcp.tool()
def knowledge_get_job(job_id: str) -> dict[str, object]:
    """Return the current status, error, item ID, and note path for an ingestion job."""
    _ensure_backend()
    response = httpx.get(
        f"{BACKEND_URL}/api/jobs/{job_id}",
        timeout=10,
        trust_env=False,
    )
    response.raise_for_status()
    return response.json()


@mcp.tool()
def knowledge_wechat_prepare(timeout_seconds: int = 120) -> dict[str, str]:
    """Initialize the logged-in macOS WeChat Channels page for link ingestion.

    Call this tool directly when the downloader client is disconnected. It
    enables the proxy and refreshes an existing Channels window automatically.
    It is not required for every supplied video URL.
    """
    timeout_seconds = max(30, min(timeout_seconds, 300))
    _ensure_downloader()
    with _temporary_wechat_proxy():
        if _channels_available():
            return {"status": "ready", "detail": "视频号本地客户端已连接"}
        _reload_wechat_channels()
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            if _channels_available():
                return {"status": "ready", "detail": "视频号本地客户端已连接"}
            time.sleep(1)
        raise RuntimeError(
            "自动刷新后视频号客户端仍未连接；"
            "请只关闭并重新打开任一视频号窗口一次，无需打开收到的具体视频链接"
        )


@mcp.tool()
def knowledge_ingest(
    content: str,
    title: str = "",
    source_url: str = "",
    timeout_seconds: int = 600,
) -> dict[str, str]:
    """Save a URL, local file path, or plain text as an AI-processed Obsidian card.

    Use `content` for the exact URL, local path, or text. `title` is optional.
    For an uploaded local file, `source_url` may preserve its original web URL.
    Returns the completed job ID and absolute Obsidian note path.
    """
    timeout_seconds = max(30, min(timeout_seconds, 1800))
    is_wechat_video = content.startswith(
        (
            "https://weixin.qq.com/sph/",
            "http://weixin.qq.com/sph/",
            "https://channels.weixin.qq.com/",
            "https://finder.video.qq.com/",
        )
    )
    _ensure_backend()
    if is_wechat_video:
        _ensure_downloader()
    command = [
        str(ROOT / ".venv" / "bin" / "python"),
        str(ROOT / "scripts" / "ingest.py"),
        content,
        "--timeout",
        str(timeout_seconds),
    ]
    if title:
        command.extend(["--title", title])
    if source_url:
        command.extend(["--source-url", source_url])
    proxy = _temporary_wechat_proxy() if is_wechat_video else nullcontext()
    with proxy:
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=timeout_seconds + 30,
        )
        if (
            is_wechat_video
            and result.returncode
            and _wechat_client_needs_refresh(result.stderr or result.stdout)
        ):
            _reload_wechat_channels()
            result = subprocess.run(
                command,
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=timeout_seconds + 30,
            )
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip())
    return _parse_result(result.stdout)


if __name__ == "__main__":
    mcp.run(transport="stdio")
