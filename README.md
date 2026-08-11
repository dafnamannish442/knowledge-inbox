# Hermes Knowledge Ingestion

Local-first、插件化的个人知识摄入系统。它把链接、文字、视频、截图、PDF
和本地文件转换成结构化 Markdown 知识卡片，并写入 Obsidian Vault，供 Hermes、
qmd 或其他本地检索工具使用。

> 当前版本是 `0.1.0-alpha`。网页和文件摄入可跨平台运行；微信视频号自动下载
> 依赖 macOS 微信客户端和本地 TLS 代理，属于实验性可选集成。

## 工作方式

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

所有来源都归一化为 `ContentItem`。新增平台只需要实现 `SourceAdapter.detect()`
和 `SourceAdapter.fetch()`，再在 `backend/adapters/registry.py` 注册。

## 支持的来源

| 来源 | 输入 | 说明 |
| --- | --- | --- |
| 网页、博客、新闻 | URL | Readability 正文提取、Markdown 转换、正文图片下载 |
| 微信公众号 | URL | 页面正文、作者和图片；也可使用其他工具先同步到 Vault |
| X / Twitter | 帖子 URL | 当前帖子、可见上文、引用内容；登录态可提高成功率 |
| YouTube | URL | 字幕优先，无字幕时使用 Whisper |
| PDF | 文件 | 文本提取；安装媒体依赖后支持扫描件 OCR |
| 图片 | 文件 | OCR；配置视觉模型后生成画面和图表描述 |
| 音视频 | 文件 | Whisper 转写或视觉模型理解 |
| 微信视频号 | 分享链接 | macOS 实验性集成，或直接上传视频文件 |
| Telegram | Webhook | 文字、caption 或正文中的首个链接 |

## 快速开始

需要 Python 3.11+。媒体处理需要 ffmpeg；OCR 需要 Tesseract。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[media,browser,hermes,dev]"
playwright install chromium
cp config.example.yaml config.yaml
uvicorn backend.main:app --host 127.0.0.1 --port 8787
```

打开 <http://127.0.0.1:8787>，或使用命令行：

```bash
.venv/bin/python scripts/ingest.py 'https://example.com/article'
.venv/bin/python scripts/ingest.py '/absolute/path/file.pdf'
.venv/bin/python scripts/ingest.py '需要保存的一段文字' --title '随手记'
```

任务也可以通过 API 提交：

```bash
curl -X POST http://127.0.0.1:8787/api/ingest \
  -H 'content-type: application/json' \
  -d '{"url":"https://example.com/article"}'
```

## 配置 AI 和 Obsidian

服务兼容 OpenAI Chat Completions API。默认关闭 AI，即使没有模型也能使用本地
降级摘要；需要 AI 分类、视觉理解和更好的标签时，通过环境变量配置：

```bash
export OBSIDIAN_VAULT_DIR=/absolute/path/to/ObsidianVault
export AI_ENABLED=true
export OPENAI_BASE_URL=http://127.0.0.1:11434/v1
export OPENAI_API_KEY=''
export OPENAI_MODEL=qwen2.5:7b
export OPENAI_VISION_MODEL=your-vision-model
```

也可以复制 `config.example.yaml` 为 `config.yaml`。`config.yaml`、`.env`、
数据库、浏览器登录态和下载媒体都已被 Git 忽略。

知识关联优先调用 qmd；找不到 qmd 时会回退到最近 1000 篇 Vault Markdown
的词法匹配。知识卡片先写临时文件，再原子替换目标文件，避免索引器读到半张卡片。

## Hermes MCP Tool

`scripts/knowledge_mcp.py` 暴露两个工具：

- `knowledge_ingest`：摄入 URL、本地文件或文字，并等待知识卡片完成。
- `knowledge_wechat_prepare`：仅在视频号本地客户端失联时刷新微信视频号窗口。

在 Hermes 的 MCP 配置中，将命令指向本仓库虚拟环境中的 Python，并把参数设置为
`scripts/knowledge_mcp.py` 的绝对路径。将
`hermes-skill/personal-knowledge-ingestion` 复制或链接到 Hermes Skill 目录后，
Hermes 就能根据“保存、收录、归档、摄入”等意图调用工具。

## Docker

```bash
cp .env.example .env
docker compose up --build
```

Docker 适合网页、文件、OCR、转写和 AI 管线。需要 macOS 微信客户端、系统代理
或 GUI 浏览器登录态时，应直接在宿主机运行后端。Compose 只把服务映射到
`127.0.0.1:8787`。

## 微信视频号安全说明

视频号集成依赖独立项目 `ltaoo/wx_channels_download`，其许可证和安全边界与本项目
不同。本仓库不分发下载器二进制、根证书、Cookies 或微信登录数据。安装、许可证、
代理和 macOS 权限说明见 `integrations/wechat-channels/README.md`。

下载器会在本机建立 TLS 代理。仅使用经过校验的官方构建，不要把下载器或本服务
暴露到局域网。MCP Tool 会在任务期间临时切换 HTTP/HTTPS 代理，并在结束后恢复
原有设置；源视频只有在 Obsidian 和 SQLite 均写入成功后才会删除。

## 验证

```bash
pytest -q
ruff check backend scripts tests
```

核心测试覆盖 Markdown 格式、任务恢复、文字端到端摄入、X 上下文、视频号 Adapter、
视频转码、写入后清理和输入分类。真实平台页面及登录态会变化，发布版本仍需单独做
平台实机验收。

## 贡献与许可证

请先阅读 `CONTRIBUTING.md` 和 `SECURITY.md`。本项目自有代码采用 Apache-2.0；
可选第三方组件继续适用各自许可证，详见 `THIRD_PARTY_NOTICES.md`。
