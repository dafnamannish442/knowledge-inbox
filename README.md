# Hermes Knowledge Ingestion

Local-first, plugin-based knowledge ingestion for Hermes, Obsidian, and other local
retrieval tools. It turns links, text, videos, screenshots, PDFs, and local files into
structured Markdown knowledge cards and saves them to an Obsidian Vault.

> Current release: `0.2.0`. Web and file ingestion run cross-platform. WeChat Channels
> downloading is an optional, experimental macOS integration that requires the desktop
> WeChat client and a local TLS proxy.

## How it works

```text
Hermes Skill / CLI / Web / Telegram
                  |
              MCP / FastAPI
                  |
             Source Adapter
                  |
             ContentItem
                  |
       Cleaner / OCR / Whisper / AI
                  |
      Classifier / Tags / Knowledge Linker
                  |
          Obsidian Markdown + SQLite
```

Every source is normalized into a `ContentItem`. To add a platform, implement
`SourceAdapter.detect()` and `SourceAdapter.fetch()`, then register the adapter in
`backend/adapters/registry.py`.

## Supported sources

| Source | Input | Capabilities |
| --- | --- | --- |
| Web pages, blogs, and news | URL | Readability extraction, Markdown conversion, and image download |
| WeChat Official Accounts | URL | Article body, author, and images; can also be synced by another tool |
| X / Twitter | Post URL | Current post, visible parent context, quoted content, and media when available |
| YouTube | URL | Captions first; Whisper fallback when captions are unavailable |
| Podcast RSS and Apple Podcasts | Feed or episode URL | Episode metadata, Podcasting 2.0 transcript, audio download, and Whisper fallback |
| Vimeo | URL | oEmbed metadata, captions when available, and Whisper fallback |
| Direct audio, video, and HLS | Media URL | Streaming download for common media files; yt-dlp resolution for `.m3u8` |
| PDF | File | Text extraction; OCR for scanned pages with the media extra |
| Images | File | OCR plus visual and chart descriptions when a vision model is configured |
| Audio and video | File | Whisper transcription or vision-model understanding |
| WeChat Channels | Share URL | Experimental macOS integration, or upload the original video directly |
| Telegram | Webhook | Text, captions, or the first URL found in a message |

## Quick start

Python 3.11 or newer is required. Media processing requires `ffmpeg`; OCR requires
Tesseract.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[media,browser,hermes,dev]"
playwright install chromium
cp config.example.yaml config.yaml
uvicorn backend.main:app --host 127.0.0.1 --port 8787
```

Open <http://127.0.0.1:8787>, or use the CLI:

```bash
.venv/bin/python scripts/ingest.py 'https://example.com/article'
.venv/bin/python scripts/ingest.py 'https://feeds.example.com/show.rss'
.venv/bin/python scripts/ingest.py 'https://vimeo.com/123456'
.venv/bin/python scripts/ingest.py '/absolute/path/file.pdf'
.venv/bin/python scripts/ingest.py 'A note to keep' --title 'Quick note'
```

The same pipeline is available through the API:

```bash
curl -X POST http://127.0.0.1:8787/api/ingest \
  -H 'content-type: application/json' \
  -d '{"url":"https://example.com/article"}'
```

## Configure AI and Obsidian

The AI layer uses an OpenAI-compatible Chat Completions endpoint. AI is disabled by
default; without a model the system still creates a local fallback summary. Enable AI
for classification, visual understanding, and richer tags:

```bash
export OBSIDIAN_VAULT_DIR=/absolute/path/to/ObsidianVault
export AI_ENABLED=true
export OPENAI_BASE_URL=http://127.0.0.1:11434/v1
export OPENAI_API_KEY=''
export OPENAI_MODEL=qwen2.5:7b
export OPENAI_VISION_MODEL=your-vision-model
```

You can set the same values in `config.yaml`. The config file, `.env`, database,
browser login state, and downloaded media are ignored by Git.

Knowledge linking uses `qmd` when available. If `qmd` is not installed, it falls back
to lexical matching over the latest 1,000 Markdown notes in the Vault. Cards are written
to a temporary file and atomically replaced so an indexer never sees a partial note.

## Hermes MCP tool

`scripts/knowledge_mcp.py` exposes two tools:

- `knowledge_ingest`: ingest a URL, local file, or text and wait for the knowledge card
  to finish.
- `knowledge_wechat_prepare`: refresh the local WeChat Channels window only when the
  client connection needs recovery.

In Hermes, configure the MCP command to use this repository's virtual-environment Python
and the absolute path to `scripts/knowledge_mcp.py`. Copy or symlink
`hermes-skill/personal-knowledge-ingestion` into the Hermes skills directory. Hermes can
then route intents such as “save”, “archive”, and “ingest” to this tool.

## Docker

```bash
cp .env.example .env
docker compose up --build
```

Docker is suitable for web pages, files, OCR, transcription, and the AI pipeline. When
the workflow needs the macOS WeChat client, system proxy, or a GUI browser login, run the
backend directly on the host. Compose binds the service to `127.0.0.1:8787`.

## WeChat Channels security boundary

The Channels integration uses the separately maintained
[`ltaoo/wx_channels_download`](https://github.com/ltaoo/wx_channels_download) project.
Its license and security boundary are separate from this repository. This project does
not distribute its binary, root certificate, cookies, or WeChat login data. See
`integrations/wechat-channels/README.md` for installation, licensing, proxy, and macOS
permission details.

The downloader creates a local TLS proxy. Use only a trusted, checksum-verified build and
never expose the downloader or this service to a LAN. The MCP tool temporarily switches
the HTTP/HTTPS proxy for the task and restores the previous settings afterward. The
original video is deleted only after both the Obsidian note and SQLite record have been
written successfully.

## Verification

```bash
pytest -q
ruff check backend scripts tests
```

The test suite covers Markdown formatting, task recovery, text end-to-end ingestion, X
context, the WeChat Channels adapter, video transcoding, post-write cleanup, and input
classification. Real platform pages and login sessions change over time, so production
deployments should still perform a separate end-to-end check for each platform they use.

## Contributing and license

Read `CONTRIBUTING.md` and `SECURITY.md` before submitting a change. Original project code
is licensed under Apache-2.0. Optional third-party components remain under their own
licenses; see `THIRD_PARTY_NOTICES.md`.
