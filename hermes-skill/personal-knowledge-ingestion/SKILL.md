---
name: personal-knowledge-ingestion
description: Save user-provided links, WeChat Channels videos, X posts, local files, screenshots, PDFs, or text into the configured Obsidian vault through the personal-knowledge MCP tools. Use when the user sends a supported URL for automatic ingestion or asks to 保存, 收录, 摄入, 归档, 总结后存入知识库, or add something to Obsidian.
---

# Personal Knowledge Ingestion

Use the `knowledge_ingest` tool when the user explicitly asks to save, ingest,
archive, or add supplied content to their personal knowledge base.

## Tool input

- `content`: pass the exact URL, absolute local file path, or original text.
- `title`: optional user-provided title. Do not invent one unless it improves a
  text-only note.
- `source_url`: only use when `content` is a local file that came from a known
  web URL.
- `timeout_seconds`: normally omit; use up to 1800 for long media.

## Behavior

- Call the tool once and wait for its result.
- Do not separately summarize the content; the ingestion pipeline performs AI
  understanding, classification, tags, linking, and Markdown formatting.
- On success, report the returned absolute `note_path`.
- On failure, report the exact actionable error and never claim the note was
  saved.
- For WeChat Channels links, the tool starts the local downloader, temporarily
  enables the approved SunnyNet proxy, and uses one logged-in Channels page as
  a local API client. It must not ask the user to open the supplied video URL.
  Never call `scripts/ingest.py` directly for these links. If
  `knowledge_ingest` reports that the client is disconnected, call
  `knowledge_wechat_prepare` immediately and retry `knowledge_ingest` after it
  returns `ready`. Do not investigate the downloader with terminal or browser
  tools, and do not invent alternative workflows. If preparation reports that
  the Hermes Python binary lacks Accessibility permission, return that exact
  binary path and the single required permission action. For any other
  preparation failure, ask the user once to close and reopen any Channels
  window; never ask them to open or play the supplied video. This bootstrap is
  needed only after WeChat or its renderer restarts. The tool always restores
  the system proxy to off and deletes the downloaded video only after the card
  and database write succeed.
- Do not call this tool for read-only questions about existing notes.
