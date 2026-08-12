# Optional WeChat Channels integration (macOS, experimental)

This integration uses the user-installed
[`ltaoo/wx_channels_download`](https://github.com/ltaoo/wx_channels_download) project to
resolve WeChat Channels share links locally. It is not required by the core service.

## Important boundaries

- The upstream project uses an MIT + Commons Clause license, which includes restrictions
  on commercial resale. Read its `LICENSE` before use.
- The downloader installs a SunnyNet root certificate and temporarily takes over the
  macOS HTTP/HTTPS proxy.
- The root certificate allows the downloader to decrypt TLS traffic routed through that
  proxy. Use only a trusted build and verify its SHA-256 checksum.
- Never commit the certificate, downloader database, WeChat data, videos, cookies, or a
  browser profile.
- Process only content you are allowed to save and analyze, and follow local laws and
  platform terms.

## Installation

1. Download a build matching your Mac architecture from the upstream Releases page and
   verify its checksum.
2. Place the downloader in a local directory, for example:

   ```text
   /absolute/path/wx_channels_download/wx_video_download
   ```

3. In the downloader's `config.yaml`, set the download directory to a controlled folder:

   ```yaml
   download:
     dir: /absolute/path/knowledge-inbox/data/originals/wechat_video
   ```

4. Configure the MCP tool:

   ```bash
   export KNOWLEDGE_WECHAT_DOWNLOADER_DIR=/absolute/path/wx_channels_download
   export KNOWLEDGE_WECHAT_DOWNLOADER_URL=http://127.0.0.1:2022
   export KNOWLEDGE_WECHAT_PROXY_PORT=2023
   export KNOWLEDGE_NETWORK_SERVICE=Wi-Fi
   ```

5. Follow the upstream instructions to install the root certificate on first use. The
   Python binary used by Hermes also needs macOS Accessibility permission so it can refresh
   an existing Channels window.

The MCP tool does not require the user to open the specific received video link. If the
local client loses its connection, the tool refreshes an already logged-in Channels
window. Initialization may be needed again only after WeChat or its renderer restarts.

## Compatibility patch

`wx_channels_download-macos-long-poll.patch` is based on upstream v260714, source commit
`3551436`, and adds an HTTPS long-poll fallback for macOS WebSocket failures. It is not a
generic patch: manually check conflicts and repeat the full acceptance test before
applying it to another upstream commit.

The patch and derivative work remain subject to the upstream license. This repository does
not distribute a patched binary.

## Acceptance criteria

A complete acceptance run must confirm all of the following:

1. A share link is resolved and downloaded to the configured directory.
2. AI produces a summary, category, tags, and knowledge links.
3. Both the Markdown note and SQLite record are written successfully.
4. The source video is deleted after success and retained after failure for retry.
5. The system HTTP/HTTPS proxy returns to the state it had before the task.
