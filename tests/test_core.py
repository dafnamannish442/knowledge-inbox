from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from runpy import run_path
from types import ModuleType, SimpleNamespace

import httpx
from fastapi import HTTPException

from backend.adapters.podcast import PodcastAdapter
from backend.adapters.registry import AdapterRegistry, build_registry
from backend.adapters.remote_media import RemoteMediaAdapter
from backend.adapters.twitter import TwitterAdapter
from backend.adapters.vimeo import VimeoAdapter
from backend.adapters.wechat_video import WeChatVideoAdapter
from backend.api.routes import ingest
from backend.config import AIConfig, AppConfig, get_config, save_storage_settings
from backend.models import ContentItem, IngestRequest, Job, JobStatus
from backend.processors.ai import AIProcessor
from backend.processors.linker import KnowledgeLinker
from backend.processors.pipeline import ContentPipeline
from backend.storage.db import Database
from backend.storage.obsidian import ObsidianWriter


def make_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        data_dir=tmp_path / "data",
        vault_dir=tmp_path / "vault",
        database_path=tmp_path / "knowledge.sqlite",
        ai=AIConfig(enabled=False),
        qmd_command="command-that-does-not-exist",
    )


def test_obsidian_format_has_required_sections() -> None:
    item = ContentItem(
        source_type="text",
        title="测试知识",
        raw_content="这是原始内容。",
        summary="一句话。",
        tags=["测试"],
        category="示例",
        related_notes=["已有知识"],
        metadata={
            "core_points": ["观点一"],
            "key_data": ["数据一"],
            "actions": ["行动一"],
        },
    )
    note = ObsidianWriter.format(item)
    for heading in (
        "# 一句话总结",
        "# 核心观点",
        "# 关键数据",
        "# 我的关联",
        "# 可行动事项",
        "# 原始内容",
    ):
        assert heading in note
    assert "[[已有知识]]" in note


def test_text_pipeline_writes_note_and_database(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.prepare()
    database = Database(config.database_path)
    database.initialize()
    pipeline = ContentPipeline(
        AdapterRegistry(),
        database,
        ObsidianWriter(config),
        AIProcessor(config.ai),
        KnowledgeLinker(config),
    )
    job = Job(
        input_type="text",
        payload={"title": "本地优先", "text": "本地优先能够控制隐私。处理链路应当可追踪。"},
    )
    item, note_path = asyncio.run(pipeline.process(job))
    assert note_path.exists()
    assert item.summary
    assert database.list_items()[0]["title"] == "本地优先"


def test_running_jobs_are_recovered_as_queued(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.prepare()
    database = Database(config.database_path)
    database.initialize()
    job = Job(input_type="text", payload={"text": "hello"}, status=JobStatus.RUNNING)
    database.save_job(job)
    assert database.recoverable_job_ids() == [job.id]
    assert database.get_job(job.id).status == JobStatus.QUEUED


def test_registry_prefers_platform_specific_adapters(tmp_path: Path) -> None:
    registry = build_registry(make_config(tmp_path))
    assert registry.for_url("https://youtu.be/abc").source_type == "youtube"
    assert registry.for_url("https://vimeo.com/123456").source_type == "vimeo"
    assert registry.for_url("https://feeds.example.com/show.rss").source_type == "podcast"
    assert registry.for_url("https://cdn.example.com/episode.mp3?download=1").source_type == "remote_media"
    assert registry.for_url("https://cdn.example.com/live/index.m3u8").source_type == "remote_media"
    assert registry.for_url("https://x.com/user/status/123").source_type == "twitter"
    assert registry.for_url("https://mp.weixin.qq.com/s/example").source_type == "wechat_article"
    assert registry.for_url("https://example.com/article").source_type == "webpage"
    assert registry.for_file(Path("scan.pdf")).source_type == "pdf"
    assert registry.for_file(Path("screen.png")).source_type == "image"
    assert registry.for_file(Path("clip.mp4")).source_type == "wechat_video"


def test_remote_media_adapter_downloads_direct_audio(tmp_path: Path, monkeypatch) -> None:
    config = make_config(tmp_path)
    downloaded = config.data_dir / "originals" / "remote_media" / "episode.mp3"

    async def fake_download(url, output_dir, max_mb, referer=None, filename=None):
        assert url == "https://cdn.example.com/episode.mp3?download=1"
        assert max_mb == config.max_download_mb
        downloaded.parent.mkdir(parents=True, exist_ok=True)
        downloaded.write_bytes(b"audio")
        return str(downloaded)

    monkeypatch.setattr("backend.adapters.remote_media.download_file", fake_download)
    fetched = asyncio.run(
        RemoteMediaAdapter(config).fetch(
            "https://cdn.example.com/episode.mp3?download=1"
        )
    )
    assert fetched.title == "episode"
    assert fetched.media_files == [str(downloaded)]
    assert fetched.metadata["capture_mode"] == "direct_download"


def test_remote_media_adapter_resolves_hls(tmp_path: Path, monkeypatch) -> None:
    config = make_config(tmp_path)
    downloaded = config.data_dir / "originals" / "remote_media" / "stream.mp4"
    downloaded.parent.mkdir(parents=True, exist_ok=True)
    downloaded.write_bytes(b"video")
    monkeypatch.setattr(RemoteMediaAdapter, "_download_hls", lambda self, url: str(downloaded))
    fetched = asyncio.run(
        RemoteMediaAdapter(config).fetch("https://cdn.example.com/live/index.m3u8")
    )
    assert fetched.media_files == [str(downloaded)]
    assert fetched.metadata["capture_mode"] == "hls"


def test_podcast_adapter_uses_rss_transcript_and_enclosure(
    tmp_path: Path, monkeypatch
) -> None:
    config = make_config(tmp_path)
    feed_url = "https://feeds.example.com/show.rss"
    transcript_url = "https://cdn.example.com/episode.vtt"
    audio_url = "https://cdn.example.com/episode.mp3"
    feed = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"
      xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"
      xmlns:podcast="https://podcastindex.org/namespace/1.0">
      <channel>
        <title>Example Show</title>
        <itunes:author>Show Author</itunes:author>
        <item>
          <title>Episode 42</title>
          <description><![CDATA[<p>Episode notes.</p>]]></description>
          <pubDate>Tue, 11 Aug 2026 12:00:00 GMT</pubDate>
          <enclosure url="https://cdn.example.com/episode.mp3" type="audio/mpeg"/>
          <podcast:transcript url="https://cdn.example.com/episode.vtt" type="text/vtt"/>
        </item>
      </channel>
    </rss>"""
    transcript = b"WEBVTT\n\n00:00:00.000 --> 00:00:02.000\nFirst point.\n\n00:00:02.000 --> 00:00:04.000\nSecond point.\n"

    async def fake_fetch_bytes(url, max_mb, referer=None):
        if url == feed_url:
            return feed, "application/rss+xml"
        assert url == transcript_url
        return transcript, "text/vtt"

    audio_path = config.data_dir / "originals" / "podcast" / "episode.mp3"

    async def fake_download(url, output_dir, max_mb, referer=None, filename=None):
        assert url == audio_url
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        audio_path.write_bytes(b"audio")
        return str(audio_path)

    monkeypatch.setattr("backend.adapters.podcast.fetch_bytes", fake_fetch_bytes)
    monkeypatch.setattr("backend.adapters.podcast.download_file", fake_download)
    fetched = asyncio.run(PodcastAdapter(config).fetch(feed_url))
    assert fetched.title == "Episode 42"
    assert fetched.author == "Show Author"
    assert fetched.raw_content == "Episode notes."
    assert fetched.transcript == "First point.\nSecond point."
    assert fetched.media_files == [str(audio_path)]
    assert fetched.metadata["show_title"] == "Example Show"


def test_podcast_adapter_resolves_specific_apple_episode(
    tmp_path: Path, monkeypatch
) -> None:
    config = make_config(tmp_path)
    source_url = "https://podcasts.apple.com/us/podcast/example/id123456?i=987654"
    audio_path = config.data_dir / "originals" / "podcast" / "selected.mp3"

    async def fake_lookup(self, catalog_id, entity):
        assert (catalog_id, entity) == ("987654", "podcastEpisode")
        return [
            {
                "kind": "podcast-episode",
                "trackName": "Selected Episode",
                "artistName": "Example Host",
                "collectionName": "Example Show",
                "description": "Selected notes.",
                "episodeUrl": "https://cdn.example.com/selected.mp3",
            }
        ]

    async def fake_download(url, output_dir, max_mb, referer=None, filename=None):
        assert url == "https://cdn.example.com/selected.mp3"
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        audio_path.write_bytes(b"audio")
        return str(audio_path)

    monkeypatch.setattr(PodcastAdapter, "_apple_lookup", fake_lookup)
    monkeypatch.setattr("backend.adapters.podcast.download_file", fake_download)
    fetched = asyncio.run(PodcastAdapter(config).fetch(source_url))
    assert fetched.title == "Selected Episode"
    assert fetched.author == "Example Host"
    assert fetched.media_files == [str(audio_path)]
    assert fetched.metadata["catalog"] == "apple_podcasts"


def test_vimeo_adapter_uses_oembed_and_resolved_captions(
    tmp_path: Path, monkeypatch
) -> None:
    config = make_config(tmp_path)
    url = "https://vimeo.com/123456"
    video_path = config.data_dir / "originals" / "vimeo" / "123456.mp4"

    async def fake_fetch_bytes(request_url, max_mb, referer=None):
        assert request_url.startswith("https://vimeo.com/api/oembed.json?")
        return (
            b'{"title":"Design Systems","author_name":"Example Studio"}',
            "application/json",
        )

    def fake_resolve(self, request_url):
        video_path.parent.mkdir(parents=True, exist_ok=True)
        video_path.write_bytes(b"video")
        return str(video_path), "Caption text.", {"duration": 120}

    monkeypatch.setattr("backend.adapters.vimeo.fetch_bytes", fake_fetch_bytes)
    monkeypatch.setattr(VimeoAdapter, "_resolve_media", fake_resolve)
    fetched = asyncio.run(VimeoAdapter(config).fetch(url))
    assert fetched.title == "Design Systems"
    assert fetched.author == "Example Studio"
    assert fetched.transcript == "Caption text."
    assert fetched.media_files == [str(video_path)]
    assert fetched.metadata["duration"] == 120


def test_twitter_adapter_keeps_parent_and_quoted_context(
    tmp_path: Path, monkeypatch
) -> None:
    html = """
    <html><head>
      <meta property="og:title" content="评论者 (@reply) on X">
      <meta property="og:description" content="只有评论">
    </head><body><main>
      <article><a href="/root/status/100">time</a><p>原帖完整内容</p></article>
      <article>
        <p>当前评论</p>
        <section><a href="/quoted/status/200">quoted</a><p>引用推文完整内容</p></section>
        <a href="/reply/status/300">time</a>
      </article>
      <article><a href="/other/status/400">time</a><p>无关回复</p></article>
    </main></body></html>
    """

    async def fake_fetch(self, url):
        return html

    monkeypatch.setattr(TwitterAdapter, "_fetch_browser_html", fake_fetch)
    fetched = asyncio.run(
        TwitterAdapter(make_config(tmp_path)).fetch(
            "https://x.com/reply/status/300?s=52"
        )
    )
    assert "原帖完整内容" in fetched.raw_content
    assert "当前评论" in fetched.raw_content
    assert "引用推文完整内容" in fetched.raw_content
    assert "无关回复" not in fetched.raw_content
    assert fetched.metadata["has_parent_context"] is True
    assert fetched.metadata["context_posts"] == 2


def test_twitter_adapter_uses_full_x_article_body(tmp_path: Path, monkeypatch) -> None:
    html = """
    <html><head>
      <meta property="og:title" content="作者 (@author) on X">
      <meta property="og:description" content="https://t.co/short">
    </head><body><main><article>
      <h1>长文标题</h1>
      <div class="x-article-body"><p>这是完整的长文正文。</p></div>
      <a href="/author/status/123">time</a>
    </article></main></body></html>
    """

    async def fake_fetch(self, url):
        return html

    monkeypatch.setattr(TwitterAdapter, "_fetch_browser_html", fake_fetch)
    fetched = asyncio.run(
        TwitterAdapter(make_config(tmp_path)).fetch("https://x.com/author/status/123")
    )
    assert fetched.title == "长文标题"
    assert "这是完整的长文正文" in fetched.raw_content
    assert fetched.metadata["extraction_mode"] == "playwright"


def test_twitter_adapter_detects_collapsed_x_article() -> None:
    assert TwitterAdapter._needs_article_expansion(
        "作者\n长文标题\n浏览量", paragraph_count=0, has_cover=True
    )
    assert not TwitterAdapter._needs_article_expansion(
        "长文标题\n" + "完整正文" * 800,
        paragraph_count=12,
        has_cover=True,
    )


def test_wechat_video_adapter_uses_local_downloader(tmp_path: Path, monkeypatch) -> None:
    config = make_config(tmp_path)
    download_dir = config.data_dir / "originals" / "wechat_video"
    download_dir.mkdir(parents=True)
    video_path = download_dir / "video.mp4"
    video_path.write_bytes(b"video")

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, path, json):
            assert path == "/api/task/create_channels"
            assert json["url"] == "https://weixin.qq.com/sph/example"
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {"id": "task-1", "file_path": str(video_path)},
                },
                request=httpx.Request("POST", "http://127.0.0.1:2022"),
            )

        async def get(self, path, params):
            assert path == "/api/task/list"
            return httpx.Response(
                200,
                json={
                    "data": {
                        "list": [
                            {
                                "id": "task-1",
                                "status": "done",
                                "meta": {"req": {"labels": {"title": "真实视频"}}},
                            }
                        ]
                    }
                },
                request=httpx.Request("GET", "http://127.0.0.1:2022"),
            )

    def fake_client(**kwargs):
        assert kwargs["trust_env"] is False
        return FakeClient()

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)
    fetched = asyncio.run(
        WeChatVideoAdapter(config).fetch("https://weixin.qq.com/sph/example")
    )
    assert fetched.title == "真实视频"
    assert fetched.media_files == [str(video_path.resolve())]


def test_wechat_video_disconnect_error_does_not_request_opening_link(
    tmp_path: Path, monkeypatch
) -> None:
    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, path, json):
            return httpx.Response(
                200,
                json={"code": 1, "msg": "初始化客户端 socket 失败"},
                request=httpx.Request("POST", "http://127.0.0.1:2022"),
            )

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: FakeClient())
    try:
        asyncio.run(
            WeChatVideoAdapter(make_config(tmp_path)).fetch(
                "https://weixin.qq.com/sph/example"
            )
        )
    except RuntimeError as error:
        assert "下载器尚未连接微信客户端" in str(error)
        assert "打开该视频" not in str(error)
    else:
        raise AssertionError("expected disconnected downloader to fail")


def test_wechat_prepare_does_not_depend_on_osascript() -> None:
    source = Path("scripts/knowledge_mcp.py").read_text(encoding="utf-8")
    assert "open_channels()" in source
    assert '"获取详情失败: 请求超时"' in source
    assert "/usr/bin/osascript" not in source
    assert "/usr/bin/swift" not in source


def load_knowledge_mcp(monkeypatch) -> dict:
    monkeypatch.setenv("KNOWLEDGE_WECHAT_PROXY_PORT", "2023")
    monkeypatch.setenv("KNOWLEDGE_NETWORK_SERVICE", "Wi-Fi")

    class FakeFastMCP:
        def __init__(self, *args, **kwargs):
            pass

        def tool(self):
            return lambda function: function

        def run(self, *args, **kwargs):
            pass

    mcp_module = ModuleType("mcp")
    server_module = ModuleType("mcp.server")
    fastmcp_module = ModuleType("mcp.server.fastmcp")
    fastmcp_module.FastMCP = FakeFastMCP
    macos_module = ModuleType("macos_wechat_channels")
    macos_module.open_channels = lambda: None
    monkeypatch.setitem(sys.modules, "mcp", mcp_module)
    monkeypatch.setitem(sys.modules, "mcp.server", server_module)
    monkeypatch.setitem(sys.modules, "mcp.server.fastmcp", fastmcp_module)
    monkeypatch.setitem(sys.modules, "macos_wechat_channels", macos_module)
    return run_path(str(Path(__file__).parents[1] / "scripts" / "knowledge_mcp.py"))


def test_mcp_exposes_cross_harness_tools(monkeypatch) -> None:
    namespace = load_knowledge_mcp(monkeypatch)
    assert callable(namespace["knowledge_ingest"])
    assert callable(namespace["knowledge_get_job"])
    assert callable(namespace["knowledge_list_capabilities"])
    assert callable(namespace["knowledge_wechat_prepare"])


def test_mcp_capabilities_are_harness_neutral(monkeypatch) -> None:
    namespace = load_knowledge_mcp(monkeypatch)
    monkeypatch.setitem(namespace["knowledge_list_capabilities"].__globals__, "_ensure_backend", lambda: None)

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "service": "knowledge-ingestion",
                "version": "0.3.0",
                "source_types": ["webpage", "podcast", "vimeo"],
                "transports": ["rest", "mcp-stdio"],
            }

    monkeypatch.setattr(namespace["httpx"], "get", lambda *args, **kwargs: Response())
    result = namespace["knowledge_list_capabilities"]()
    assert result["service"] == "knowledge-ingestion"
    assert "podcast" in result["source_types"]
    assert "Hermes" not in json.dumps(result)


def test_mcp_get_job_returns_backend_state(monkeypatch) -> None:
    namespace = load_knowledge_mcp(monkeypatch)
    monkeypatch.setitem(namespace["knowledge_get_job"].__globals__, "_ensure_backend", lambda: None)

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "job-1", "status": "succeeded", "note_path": "/vault/note.md"}

    monkeypatch.setattr(namespace["httpx"], "get", lambda *args, **kwargs: Response())
    assert namespace["knowledge_get_job"]("job-1")["note_path"] == "/vault/note.md"


def test_wechat_proxy_parser(monkeypatch) -> None:
    namespace = load_knowledge_mcp(monkeypatch)
    subprocess_module = namespace["subprocess"]
    monkeypatch.setattr(
        subprocess_module,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout="Enabled: Yes\nServer: 127.0.0.1\nPort: 7897\n"
        ),
    )
    settings = namespace["_read_proxy"]("")
    assert settings.enabled is True
    assert settings.server == "127.0.0.1"
    assert settings.port == "7897"


def test_wechat_proxy_can_disable_empty_previous_settings(monkeypatch) -> None:
    namespace = load_knowledge_mcp(monkeypatch)
    commands = []
    monkeypatch.setattr(
        namespace["subprocess"],
        "run",
        lambda command, **kwargs: commands.append(command) or SimpleNamespace(stdout=""),
    )

    namespace["_configure_proxy"]("", "", "0", False)

    assert commands == [
        ["/usr/sbin/networksetup", "-setwebproxystate", "Wi-Fi", "off"]
    ]


def test_service_start_creates_log_directory(tmp_path: Path, monkeypatch) -> None:
    namespace = load_knowledge_mcp(monkeypatch)
    start_service = namespace["_start_service"]
    start_globals = start_service.__globals__
    reachable = iter([False, True])
    popen_calls = []
    monkeypatch.setitem(start_globals, "ROOT", tmp_path)
    monkeypatch.setitem(start_globals, "_reachable", lambda url: next(reachable))
    monkeypatch.setattr(
        namespace["subprocess"],
        "Popen",
        lambda command, **kwargs: popen_calls.append((command, kwargs))
        or SimpleNamespace(),
    )

    start_service(["service"], tmp_path, "http://127.0.0.1/health", "service.log")

    assert (tmp_path / "data" / "service.log").exists()
    assert popen_calls[0][1]["stdout"].closed is True


def test_wechat_proxy_restores_previous_state_after_error(monkeypatch) -> None:
    namespace = load_knowledge_mcp(monkeypatch)
    proxy_settings = namespace["ProxySettings"]
    context = namespace["_temporary_wechat_proxy"]
    calls = []
    previous = {
        "": proxy_settings(True, "127.0.0.1", "7897"),
        "secure": proxy_settings(False, "proxy.example", "8080"),
    }
    context_globals = context.__wrapped__.__globals__
    monkeypatch.setitem(context_globals, "_read_proxy", lambda secure: previous[secure])
    monkeypatch.setitem(
        context_globals,
        "_configure_proxy",
        lambda secure, server, port, enabled: calls.append(
            (secure, server, port, enabled)
        ),
    )

    try:
        with context():
            raise RuntimeError("simulated ingestion failure")
    except RuntimeError:
        pass

    assert calls == [
        ("", "127.0.0.1", "2023", True),
        ("secure", "127.0.0.1", "2023", True),
        ("", "127.0.0.1", "7897", True),
        ("secure", "proxy.example", "8080", False),
    ]


def test_ai_transcodes_hevc_mp4_for_vision_model(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "video.mp4"
    source.write_bytes(b"hevc")
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        if command[0] == "ffprobe":
            return SimpleNamespace(stdout="hevc\n")
        Path(command[-1]).write_bytes(b"h264")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr("backend.processors.ai.subprocess.run", fake_run)
    prepared = AIProcessor._prepare_video(source)
    try:
        assert prepared != source
        assert [command[0] for command in commands] == ["ffprobe", "ffmpeg"]
    finally:
        prepared.unlink(missing_ok=True)


def test_uploaded_file_keeps_original_source_url(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    source = tmp_path / "note.txt"
    source.write_text("原始内容", encoding="utf-8")
    pipeline = ContentPipeline(
        build_registry(config),
        Database(config.database_path),
        ObsidianWriter(config),
        AIProcessor(config.ai),
        KnowledgeLinker(config),
    )
    item = asyncio.run(
        pipeline._extract(
            Job(
                input_type="file",
                payload={
                    "path": str(source),
                    "source_url": "https://example.com/original",
                },
            )
        )
    )
    assert item.source_url == "https://example.com/original"


def test_successful_video_ingest_deletes_source_when_enabled(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config.delete_video_after_ingest = True
    config.prepare()
    source = config.data_dir / "originals" / "uploads" / "video.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"video")
    database = Database(config.database_path)
    database.initialize()

    class FakeVideoAI:
        supports_video = True

        async def analyze(self, item):
            return AIProcessor._fallback("视频内容")

    pipeline = ContentPipeline(
        build_registry(config),
        database,
        ObsidianWriter(config),
        FakeVideoAI(),
        KnowledgeLinker(config),
    )
    item, note_path = asyncio.run(
        pipeline.process(Job(input_type="file", payload={"path": str(source)}))
    )
    assert note_path.exists()
    assert not source.exists()
    assert item.media_files == []
    assert item.metadata["deleted_video_files"] == ["video.mp4"]


def test_ingest_script_classifies_url_file_and_text(tmp_path: Path) -> None:
    classify_input = run_path(
        str(Path(__file__).parents[1] / "scripts" / "ingest.py")
    )["classify_input"]
    source = tmp_path / "note.txt"
    source.write_text("内容", encoding="utf-8")
    assert classify_input("https://example.com") == ("url", "https://example.com")
    assert classify_input(str(source)) == ("file", source)
    assert classify_input("一段文字") == ("text", "一段文字")


def test_frontend_uses_one_unified_inbox() -> None:
    html = Path("frontend/index.html").read_text(encoding="utf-8")
    assert html.count('<form id="inbox-form"') == 1
    assert 'id="inbox-input"' in html
    assert 'id="file-input"' in html
    assert "extractSingleUrl" in html
    assert 'id="storage-dialog"' in html
    assert "/api/settings/storage" in html
    assert "if (!storageConfigured) event.preventDefault()" in html
    assert all(old_id not in html for old_id in ("url-form", "file-form", "text-form"))


def test_storage_settings_are_validated_and_persisted(tmp_path: Path) -> None:
    config = AppConfig(data_dir=tmp_path / "data")
    vault = tmp_path / "vault"
    vault.mkdir()

    save_storage_settings(config, str(vault), "Knowledge/Inbox")

    assert config.vault_dir == vault.resolve()
    assert config.inbox_folder == "Knowledge/Inbox"
    assert (vault / "Knowledge" / "Inbox").is_dir()
    assert "Knowledge/Inbox" in config.storage_config_path.read_text("utf-8")


def test_storage_settings_reject_unsafe_paths(tmp_path: Path) -> None:
    config = AppConfig(data_dir=tmp_path / "data")
    vault = tmp_path / "vault"
    vault.mkdir()

    for vault_dir, inbox_folder in (("relative", "Inbox"), (str(vault), "../Outside")):
        try:
            save_storage_settings(config, vault_dir, inbox_folder)
        except ValueError:
            pass
        else:
            raise AssertionError("expected unsafe storage settings to fail")


def test_storage_settings_reload_from_local_file(tmp_path: Path, monkeypatch) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(f"data_dir: {tmp_path / 'data'}\n", encoding="utf-8")
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("KNOWLEDGE_CONFIG", str(config_path))

    get_config.cache_clear()
    first = get_config()
    assert not first.storage_configured
    save_storage_settings(first, str(vault), "Cards")
    get_config.cache_clear()

    loaded = get_config()
    assert loaded.vault_dir == vault.resolve()
    assert loaded.inbox_folder == "Cards"
    get_config.cache_clear()


def test_ingest_rejects_unconfigured_storage(tmp_path: Path) -> None:
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(config=AppConfig(data_dir=tmp_path / "data"))
        )
    )

    try:
        asyncio.run(ingest(IngestRequest(text="hello"), request))
    except HTTPException as error:
        assert error.status_code == 409
        assert "配置知识库文件夹" in error.detail
    else:
        raise AssertionError("expected unconfigured ingestion to fail")


def test_cross_harness_skills_support_automatic_forwarded_content() -> None:
    for harness in ("codex", "hermes", "openclaw"):
        skill = Path(
            f"clients/{harness}/knowledge-ingestion/SKILL.md"
        ).read_text(encoding="utf-8")
        assert "standalone supported link" in skill
        assert "context for a question" in skill
