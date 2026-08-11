from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from markdownify import markdownify

from backend.adapters.base import FetchedContent, SourceAdapter
from backend.adapters.utils import download_file, fetch_bytes, subtitle_to_text


class PodcastAdapter(SourceAdapter):
    source_type = "podcast"
    _feed_hosts = {
        "feeds.buzzsprout.com",
        "feeds.megaphone.fm",
        "feeds.simplecast.com",
        "feeds.transistor.fm",
        "rss.art19.com",
    }

    @classmethod
    def detect(cls, value: str | Path) -> bool:
        if not isinstance(value, str) or not value.startswith(("http://", "https://")):
            return False
        parsed = urlparse(value)
        host = (parsed.hostname or "").lower()
        path = parsed.path.lower().rstrip("/")
        return (
            host == "podcasts.apple.com"
            or host in cls._feed_hosts
            or host.startswith(("feeds.", "rss."))
            or path.endswith((".rss", ".xml"))
            or path.endswith(("/feed", "/rss"))
            or path.endswith("/podcast/rss")
        )

    async def fetch(self, value: str | Path, **kwargs: object) -> FetchedContent:
        source_url = str(value)
        if (urlparse(source_url).hostname or "").lower() == "podcasts.apple.com":
            episode = await self._apple_episode(source_url, kwargs.get("title"))
            if episode:
                return episode
            feed_url = await self._apple_feed_url(source_url)
        else:
            feed_url = source_url
        body, _ = await fetch_bytes(feed_url, max_mb=10, referer=source_url)
        return await self._from_rss(body, source_url, feed_url, kwargs.get("title"))

    async def _from_rss(
        self,
        body: bytes,
        source_url: str,
        feed_url: str,
        title_override: object,
    ) -> FetchedContent:
        try:
            root = ET.fromstring(body)
        except ET.ParseError as error:
            raise RuntimeError("Podcast URL 未返回有效的 RSS Feed") from error
        channel = next((node for node in root.iter() if self._local(node.tag) == "channel"), None)
        if channel is None:
            raise RuntimeError("Podcast RSS 缺少 channel")
        items = [node for node in channel if self._local(node.tag) == "item"]
        if not items:
            raise RuntimeError("Podcast RSS 中没有可摄入的单集")
        episode = self._select_episode(items, source_url)
        episode_title = self._text(episode, "title") or "Podcast episode"
        description = self._text(episode, "encoded", "description") or ""
        raw_content = markdownify(description, heading_style="ATX", strip=["script", "style"]).strip()
        enclosure = self._element(episode, "enclosure")
        media_url = enclosure.get("url") if enclosure is not None else None
        transcript_node = self._element(episode, "transcript")
        transcript_url = transcript_node.get("url") if transcript_node is not None else None
        transcript = await self._fetch_transcript(transcript_url, feed_url)

        media_files: list[str] = []
        if media_url and self.config.download_remote_media:
            media_files.append(
                await download_file(
                    media_url,
                    self.config.data_dir / "originals" / "podcast",
                    self.config.max_download_mb,
                    referer=feed_url,
                    filename=episode_title,
                )
            )
        return FetchedContent(
            source_type=self.source_type,
            source_url=source_url,
            title=str(title_override or episode_title),
            author=(
                self._text(episode, "author", "creator")
                or self._text(channel, "author", "managingEditor")
            ),
            raw_content=raw_content,
            transcript=transcript,
            media_files=media_files,
            metadata={
                "show_title": self._text(channel, "title"),
                "published": self._text(episode, "pubDate", "published"),
                "episode_url": self._text(episode, "link", "guid"),
                "feed_url": feed_url,
                "media_url": media_url,
                "transcript_url": transcript_url,
            },
        )

    async def _apple_episode(
        self, source_url: str, title_override: object
    ) -> FetchedContent | None:
        episode_id = (parse_qs(urlparse(source_url).query).get("i") or [None])[0]
        if not episode_id or not episode_id.isdigit():
            return None
        results = await self._apple_lookup(episode_id, "podcastEpisode")
        episode = next(
            (result for result in results if result.get("kind") == "podcast-episode"),
            None,
        )
        if not episode or not episode.get("episodeUrl"):
            return None
        title = str(title_override or episode.get("trackName") or "Podcast episode")
        media_files: list[str] = []
        if self.config.download_remote_media:
            media_files.append(
                await download_file(
                    str(episode["episodeUrl"]),
                    self.config.data_dir / "originals" / "podcast",
                    self.config.max_download_mb,
                    referer=source_url,
                    filename=title,
                )
            )
        return FetchedContent(
            source_type=self.source_type,
            source_url=source_url,
            title=title,
            author=episode.get("artistName"),
            raw_content=str(episode.get("description") or ""),
            media_files=media_files,
            metadata={
                "show_title": episode.get("collectionName"),
                "published": episode.get("releaseDate"),
                "media_url": episode.get("episodeUrl"),
                "duration_ms": episode.get("trackTimeMillis"),
                "catalog": "apple_podcasts",
            },
        )

    async def _apple_feed_url(self, source_url: str) -> str:
        match = re.search(r"/id(\d+)", urlparse(source_url).path)
        if not match:
            raise RuntimeError("无法从 Apple Podcasts URL 识别节目 ID")
        results = await self._apple_lookup(match.group(1), "podcast")
        feed_url = next(
            (str(result["feedUrl"]) for result in results if result.get("feedUrl")),
            None,
        )
        if not feed_url:
            raise RuntimeError("Apple Podcasts 未返回公开 RSS Feed")
        return feed_url

    @staticmethod
    async def _apple_lookup(catalog_id: str, entity: str) -> list[dict]:
        query = urlencode({"id": catalog_id, "entity": entity})
        body, _ = await fetch_bytes(f"https://itunes.apple.com/lookup?{query}", max_mb=2)
        try:
            return list(json.loads(body).get("results") or [])
        except (json.JSONDecodeError, AttributeError) as error:
            raise RuntimeError("Apple Podcasts Lookup API 返回无效数据") from error

    async def _fetch_transcript(self, url: str | None, referer: str) -> str | None:
        if not url:
            return None
        try:
            body, _ = await fetch_bytes(url, max_mb=20, referer=referer)
        except (httpx.HTTPError, ValueError):
            return None
        return subtitle_to_text(body.decode("utf-8", errors="replace"))

    @classmethod
    def _select_episode(cls, items: list[ET.Element], source_url: str) -> ET.Element:
        normalized = source_url.rstrip("/")
        for item in items:
            if any(
                (cls._text(item, name) or "").rstrip("/") == normalized
                for name in ("link", "guid")
            ):
                return item
        return items[0]

    @classmethod
    def _text(cls, element: ET.Element, *names: str) -> str | None:
        for child in element:
            if cls._local(child.tag) in names and child.text and child.text.strip():
                return child.text.strip()
        return None

    @classmethod
    def _element(cls, element: ET.Element, name: str) -> ET.Element | None:
        return next((child for child in element if cls._local(child.tag) == name), None)

    @staticmethod
    def _local(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]
