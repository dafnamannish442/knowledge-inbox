# Knowledge Ingestion Service

[English](README.md) | **简体中文**

面向 Obsidian 和其他本地检索工具的中立 Harness、本地优先知识摄入服务。它把链接、文字、视频、截图、PDF 和本地文件转换成结构化 Markdown 知识卡片。Hermes、Codex、OpenClaw 及其他 MCP 客户端共用同一套 Adapter 和处理服务。

> 当前版本：`0.3.0`。网页与文件摄入支持跨平台运行。微信视频号下载是可选的实验性 macOS 集成，需要桌面微信和本地 TLS 代理。

## 工作原理

```text
Hermes / Codex / OpenClaw / CLI / Web / Telegram
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

所有来源都会统一转换成 `ContentItem`。新增平台时，实现 `SourceAdapter.detect()` 和 `SourceAdapter.fetch()`，再把 Adapter 注册到 `backend/adapters/registry.py`。

## 支持的来源

| 来源 | 输入 | 能力 |
| --- | --- | --- |
| 网页、博客、新闻 | URL | Readability 正文提取、Markdown 转换和图片下载 |
| 微信公众号 | URL | 正文、作者和图片；也可以由其他工具预先同步 |
| X / Twitter | 帖子 URL | 当前帖子、可见的上文、引用内容和媒体 |
| YouTube | URL | 优先使用字幕；没有字幕时回退到 Whisper |
| Podcast RSS 与 Apple Podcasts | Feed 或单集 URL | 单集信息、Podcasting 2.0 transcript、音频下载和 Whisper 回退 |
| Vimeo | URL | oEmbed 信息、可用字幕和 Whisper 回退 |
| 直接音视频与 HLS | 媒体 URL | 常见媒体流下载；通过 yt-dlp 解析 `.m3u8` |
| PDF | 文件 | 文本提取；安装 media extra 后支持扫描页 OCR |
| 图片 | 文件 | OCR；配置视觉模型后提供画面与图表描述 |
| 音频和视频 | 文件 | Whisper 转写或视觉模型理解 |
| 微信视频号 | 分享链接 | 实验性 macOS 集成，也可以直接上传原始视频 |
| Telegram | Webhook | 文字、caption 或消息中的第一个 URL |

## 快速开始

需要 Python 3.11 或更高版本。媒体处理需要 `ffmpeg`，OCR 需要 Tesseract。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[media,browser,mcp,dev]"
playwright install chromium
cp config.example.yaml config.yaml
uvicorn backend.main:app --host 127.0.0.1 --port 8787
```

打开 <http://127.0.0.1:8787>。在同一个输入区粘贴链接或文字，或者拖入视频、截图、PDF 和本地文件；来源识别、AI 处理、分类、标签、关联和 Obsidian 写入均自动完成。点击右上角 **EN / 中** 可切换网页语言；点击“最近生成”里的已完成记录，会用系统文件管理器打开对应知识卡片所在的文件夹。

macOS 首次启动时，可用系统原生文件夹选择器选择已有的 Obsidian Vault 或 Markdown 文件夹，再设置卡片子目录。服务会验证写入权限，并且只把这两个值保存到已忽略的本地文件 `data/storage.yaml`。以后可通过“设置”修改。如果 Docker 或管理员设置了 `OBSIDIAN_VAULT_DIR`，网页设置会变成只读。其他宿主系统可在同一对话框里输入绝对路径。

手机端的主要流程是把内容转发到连接 Agent Harness 的 Telegram、Discord 或其他 IM。Harness 会调用 `knowledge_ingest`，不需要网页表单，也不用再补一句“保存”。作为普通问题上下文的链接不会自动归档。桌面端的一键浏览器扩展是自然的后续客户端，目前尚未包含。

也可以使用 CLI：

```bash
.venv/bin/python scripts/ingest.py 'https://example.com/article'
.venv/bin/python scripts/ingest.py 'https://feeds.example.com/show.rss'
.venv/bin/python scripts/ingest.py 'https://vimeo.com/123456'
.venv/bin/python scripts/ingest.py '/absolute/path/file.pdf'
.venv/bin/python scripts/ingest.py '需要保存的文字' --title '随手记'
```

同一条 Pipeline 也通过 API 提供：

```bash
curl -X POST http://127.0.0.1:8787/api/ingest \
  -H 'content-type: application/json' \
  -d '{"url":"https://example.com/article"}'
```

## 配置 AI 与 Obsidian

AI 层使用 OpenAI Compatible Chat Completions 接口。AI 默认关闭；不配置模型时，系统仍会生成本地回退摘要。开启 AI 后可获得分类、视觉理解和更丰富的标签：

```bash
export OBSIDIAN_VAULT_DIR=/absolute/path/to/ObsidianVault
export AI_ENABLED=true
export OPENAI_BASE_URL=http://127.0.0.1:11434/v1
export OPENAI_API_KEY=''
export OPENAI_MODEL=qwen2.5:7b
export OPENAI_VISION_MODEL=your-vision-model
```

也可以在 `config.yaml` 设置相同的值。配置文件、`.env`、数据库、浏览器登录态和下载媒体均被 Git 忽略。

知识关联会优先使用 `qmd`。没有安装 `qmd` 时，系统回退到对 Vault 最近 1,000 篇 Markdown 的词法匹配。卡片先写入临时文件，再原子替换，避免索引器读到半张卡片。

## MCP Tool 与 Harness 客户端

`scripts/knowledge_mcp.py` 是中立 Harness 的 stdio MCP 服务，提供：

- `knowledge_ingest`：摄入 URL、本地文件或文字，并等待知识卡片完成。
- `knowledge_get_job`：查看已知摄入任务的当前状态。
- `knowledge_list_capabilities`：列出支持的来源与输入类型。
- `knowledge_wechat_prepare`：仅在微信视频号客户端连接需要恢复时刷新本地窗口。

每个 Harness 都使用包含 `mcp` extra 的 Python 环境和 `scripts/knowledge_mcp.py` 绝对路径启动同一个服务。`clients/hermes`、`clients/codex` 和 `clients/openclaw` 只包含各客户端的路由说明，不重复实现 Adapter。安装命令见 `clients/README.md`。

## Docker

```bash
cp .env.example .env
docker compose up --build
```

Docker 适合网页、文件、OCR、转写和 AI Pipeline。需要 macOS 微信客户端、系统代理或 GUI 浏览器登录时，请直接在宿主机运行后端。Compose 将服务绑定到 `127.0.0.1:8787`。

## 微信视频号安全边界

视频号集成使用独立维护的 [`ltaoo/wx_channels_download`](https://github.com/ltaoo/wx_channels_download)。它的许可证和安全边界独立于本仓库。本项目不会分发它的二进制、根证书、Cookie 或微信登录数据。安装、许可证、代理和 macOS 权限说明见 `integrations/wechat-channels/README.md`。

下载器会创建本地 TLS 代理。只应使用可信并核验校验值的构建，且不要把下载器或本服务暴露到局域网。MCP Tool 会在任务期间临时切换 HTTP/HTTPS 代理，并在结束后恢复。只有 Obsidian 卡片和 SQLite 记录都成功写入后，才会删除原始视频。

## 验证

```bash
pytest -q
ruff check backend scripts tests
```

测试覆盖 Markdown 格式、任务恢复、文字端到端摄入、X 上下文、微信视频号 Adapter、视频转码、写入后清理和输入分类。真实平台页面与登录会随时间变化，因此生产部署仍应对实际使用的平台分别执行端到端检查。

## 贡献与许可证

提交修改前请阅读 `CONTRIBUTING.md` 和 `SECURITY.md`。项目原创代码使用 Apache-2.0；可选第三方组件沿用各自许可证，详见 `THIRD_PARTY_NOTICES.md`。
