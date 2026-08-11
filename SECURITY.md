# Security Policy

## Reporting a vulnerability

请不要在公开 Issue 中提交密钥、登录态、浏览器 Profile、下载媒体或可复现的私人
内容。请通过仓库维护者在 GitHub 上提供的私密安全报告渠道提交漏洞。

## Local security boundary

- FastAPI 和 Docker Compose 默认只监听本机回环地址。
- 不要提交 `config.yaml`、`.env`、`data/` 或 Playwright Profile。
- API Key 只通过环境变量或本机忽略文件提供。
- 微信视频号集成会临时改变 macOS HTTP/HTTPS 代理，并安装第三方根证书；它是
  高权限可选功能，应只在专用或可接受风险的微信账号上使用。
- 不要把 `wx_channels_download` 的 API、代理端口或本服务暴露到不受信任网络。
- 升级下载器前应重新核对来源、版本和 SHA-256。

如果凭据曾经进入 Git 历史，仅从最新文件删除是不够的：应先撤销凭据，再清理历史。
