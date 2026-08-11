from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urljoin, urlparse
from uuid import uuid4

import httpx


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
)


async def fetch_bytes(url: str, max_mb: int, referer: str | None = None) -> tuple[bytes, str]:
    headers = {"User-Agent": USER_AGENT}
    if referer:
        headers["Referer"] = referer
    async with httpx.AsyncClient(follow_redirects=True, timeout=45, headers=headers) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            limit = max_mb * 1024 * 1024
            chunks: list[bytes] = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > limit:
                    raise ValueError(f"下载超过 {max_mb} MB 限制")
                chunks.append(chunk)
            return b"".join(chunks), response.headers.get("content-type", "")


async def fetch_html(url: str, user_data_dir: Path | None = None) -> str:
    if user_data_dir:
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as playwright:
                context = await playwright.chromium.launch_persistent_context(
                    str(user_data_dir), headless=True
                )
                page = context.pages[0] if context.pages else await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                await page.wait_for_timeout(2_000)
                html = await page.content()
                await context.close()
                return html
        except ImportError:
            pass

    body, _ = await fetch_bytes(url, max_mb=20)
    return body.decode("utf-8", errors="replace")


def safe_filename(value: str, fallback: str = "file") -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", value).strip(" .")
    return cleaned[:100] or fallback


def media_extension(url: str, content_type: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix and len(suffix) <= 6:
        return suffix
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "video/mp4": ".mp4",
    }.get(content_type.split(";")[0].lower(), ".bin")


async def download_media(
    urls: list[str], source_url: str, output_dir: Path, max_mb: int, limit: int = 20
) -> list[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[str] = []
    seen: set[str] = set()
    for raw_url in urls[:limit]:
        url = urljoin(source_url, raw_url)
        if url in seen or not url.startswith(("http://", "https://")):
            continue
        seen.add(url)
        try:
            content, content_type = await fetch_bytes(url, max_mb=max_mb, referer=source_url)
            suffix = media_extension(url, content_type)
            path = output_dir / f"{uuid4().hex}{suffix}"
            path.write_bytes(content)
            results.append(str(path))
        except (httpx.HTTPError, ValueError):
            continue
    return results
