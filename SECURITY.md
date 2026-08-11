# Security policy

## Reporting a vulnerability

Do not submit API keys, login sessions, browser profiles, downloaded media, or private
content in a public Issue. Use GitHub's private security reporting channel to contact the
maintainer.

## Local security boundary

- FastAPI and Docker Compose listen on the local loopback interface by default.
- Never commit `config.yaml`, `.env`, `data/`, or a Playwright profile.
- Provide API keys only through environment variables or an ignored local config file.
- The WeChat Channels integration temporarily changes the macOS HTTP/HTTPS proxy and
  installs a third-party root certificate. It is a high-privilege optional feature and
  should be used only with a dedicated or otherwise acceptable-risk WeChat account.
- Do not expose `wx_channels_download`, its API, its proxy port, or this service to an
  untrusted network.
- Re-check the source, version, and SHA-256 checksum before upgrading the downloader.

If a credential has ever entered Git history, deleting it from the latest files is not
enough. Revoke the credential first, then remove it from history.
