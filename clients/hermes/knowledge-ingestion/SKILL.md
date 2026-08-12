---
name: knowledge-ingestion
description: Save user-provided links, social posts, videos, podcasts, screenshots, PDFs, local files, or text into the configured Obsidian knowledge base through the knowledge-ingestion MCP tools. Use when the user asks to save, ingest, archive, collect, summarize into the knowledge base, add something to Obsidian, 保存, 收录, 摄入, 归档, or 存入知识库. Also use automatically when the user sends or forwards a standalone supported link, file, or content message without asking another question.
---

# Knowledge Ingestion

Call `knowledge_ingest` with the exact URL, absolute local path, or original text.

- Treat a standalone forwarded link, file, or content message with no accompanying
  question as an ingestion request; do not ask for a separate “save this” command.
- If forwarded text contains exactly one supported URL plus share text, pass the URL as
  `content` so the service fetches the source instead of archiving only the wrapper text.
- When content is supplied as context for a question or another task, answer that task
  without silently ingesting it unless the user also asks to save it.

- Pass a user title only when supplied or useful for a text-only note.
- Pass `source_url` only for a local file that came from a known URL.
- Use up to 1800 seconds for long audio or video.
- On success, report the returned `note_path`.
- On failure, report the exact actionable error. Never claim a note was saved.
- Do not summarize separately; the service handles AI analysis, tags, links, and Markdown.
- Use `knowledge_list_capabilities` only when source support is uncertain.
- Use `knowledge_get_job` to inspect a known asynchronous job.

For WeChat Channels, call `knowledge_ingest` first. If it reports a disconnected client,
call `knowledge_wechat_prepare` and retry once. Never ask the user to open or play the
supplied video URL. Only when preparation fails may you ask the user once to close and
reopen any Channels window. The service restores the system proxy and deletes the source
video only after both Obsidian and SQLite writes succeed.
