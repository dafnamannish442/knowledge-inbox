# 微信视频号可选集成（macOS，实验性）

本集成通过用户自行安装的
[`ltaoo/wx_channels_download`](https://github.com/ltaoo/wx_channels_download)
在本机解析视频号分享链接。它不是核心服务的必需依赖。

## 重要边界

- 上游采用 MIT + Commons Clause，包含商业销售限制；请先阅读其 LICENSE。
- 下载器需要安装 SunnyNet 根证书并临时接管 macOS HTTP/HTTPS 代理。
- 根证书允许下载器解密经过代理的 TLS 流量。仅使用可信来源的构建，并核验 SHA-256。
- 不要提交证书、下载器数据库、微信数据、视频、Cookie 或浏览器 Profile。
- 只处理你有权保存和分析的内容，并遵守所在地区法律及平台条款。

## 安装

1. 从上游 Releases 下载与你的 Mac 架构匹配的构建并核对校验值。
2. 将下载器放在本机目录，例如：

   ```text
   /absolute/path/wx_channels_download/wx_video_download
   ```

3. 在下载器的 `config.yaml` 中，把下载目录设置到本项目的受控目录：

   ```yaml
   download:
     dir: /absolute/path/hermes-knowledge-ingestion/data/originals/wechat_video
   ```

4. 配置 MCP Tool：

   ```bash
   export KNOWLEDGE_WECHAT_DOWNLOADER_DIR=/absolute/path/wx_channels_download
   export KNOWLEDGE_WECHAT_DOWNLOADER_URL=http://127.0.0.1:2022
   export KNOWLEDGE_WECHAT_PROXY_PORT=2023
   export KNOWLEDGE_NETWORK_SERVICE=Wi-Fi
   ```

5. 首次使用按照上游说明安装根证书。Hermes 所使用的 Python 还需要 macOS
   “隐私与安全性 → 辅助功能”权限，才能刷新现有视频号窗口。

MCP Tool 不要求用户打开收到的具体视频链接。若本地客户端失联，它会刷新已经登录的
视频号窗口；只有微信或渲染进程重启后才可能再次需要初始化。

## 兼容补丁

`wx_channels_download-macos-long-poll.patch` 基于上游 v260714、源码提交
`3551436`，为 macOS WebSocket 连接失败的情况增加 HTTPS long-poll fallback。
它不是通用补丁，应用到其他提交前必须人工检查冲突并重新做完整验收。

补丁及其衍生部分继续适用上游许可证。本仓库不提供补丁后的二进制。

## 验收要求

一次完整验收必须同时确认：

1. 分享链接被解析并下载到配置目录。
2. AI 生成摘要、分类、标签和知识关联。
3. Markdown 与 SQLite 均写入成功。
4. 成功后源视频被删除；失败时保留以便重试。
5. 系统 HTTP/HTTPS 代理恢复到调用前状态。
