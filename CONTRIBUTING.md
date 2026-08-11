# Contributing

欢迎修复 Bug、改进文档和新增 Source Adapter。

## 开发环境

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[media,browser,hermes,dev]"
pytest -q
ruff check backend scripts tests
```

## 新增 Adapter

1. 在 `backend/adapters/` 继承 `SourceAdapter`。
2. 实现 `detect()` 和 `fetch()`，返回 `FetchedContent`。
3. 在 `backend/adapters/registry.py` 注册，专用 Adapter 必须排在通用网页 Adapter 前。
4. 为检测、正文提取和失败路径增加离线测试。

Pull Request 不应包含真实账号、Cookie、密钥、本机绝对路径、媒体文件、下载器二进制
或由目标平台抓取的受版权保护样本。测试 Fixture 请使用最小的合成内容。
