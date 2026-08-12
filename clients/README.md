# Harness clients

The backend, adapters, AI pipeline, and Obsidian writer run once. Every Harness launches
the same stdio MCP server and installs only a small routing Skill.

Set these paths for your installation:

```bash
export KNOWLEDGE_REPO=/absolute/path/knowledge-ingestion
export KNOWLEDGE_MCP_PYTHON=/absolute/path/python-with-mcp-installed
```

## Codex

```bash
codex mcp add knowledge-ingestion -- \
  "$KNOWLEDGE_MCP_PYTHON" "$KNOWLEDGE_REPO/scripts/knowledge_mcp.py"
cp -R "$KNOWLEDGE_REPO/clients/codex/knowledge-ingestion" \
  "$HOME/.codex/skills/knowledge-ingestion"
```

Restart Codex after installing a new Skill or MCP server.

## OpenClaw

```bash
openclaw mcp add knowledge-ingestion \
  --command "$KNOWLEDGE_MCP_PYTHON" \
  --arg "$KNOWLEDGE_REPO/scripts/knowledge_mcp.py" \
  --cwd "$KNOWLEDGE_REPO" \
  --timeout 1800
openclaw skills install \
  "$KNOWLEDGE_REPO/clients/openclaw/knowledge-ingestion" \
  --global --as knowledge-ingestion
openclaw mcp reload
```

## Hermes

Add a stdio server named `knowledge-ingestion` under `mcp_servers` in the selected Hermes
profile, using the same Python command and script path. Copy
`clients/hermes/knowledge-ingestion` to the shared Hermes Skills directory, then run:

```bash
hermes mcp test knowledge-ingestion
```

All three clients should discover the same tools:

- `knowledge_ingest`
- `knowledge_get_job`
- `knowledge_list_capabilities`
- `knowledge_wechat_prepare`
