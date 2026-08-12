# Contributing

Bug fixes, documentation improvements, and new source adapters are welcome.

## Development environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[media,browser,mcp,dev]"
pytest -q
ruff check backend scripts tests
```

## Adding an adapter

1. Add a `SourceAdapter` implementation under `backend/adapters/`.
2. Implement `detect()` and `fetch()`, returning `FetchedContent`.
3. Register it in `backend/adapters/registry.py`. A specialized adapter must be listed
   before the generic web adapter.
4. Add offline tests for detection, content extraction, and failure paths.

Pull requests must not include real accounts, cookies, API keys, local absolute paths,
media files, downloader binaries, or copyrighted samples captured from a target platform.
Use small synthetic fixtures instead.
