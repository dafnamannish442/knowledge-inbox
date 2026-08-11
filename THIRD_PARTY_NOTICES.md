# Third-party notices

Licenses for Python dependencies are maintained by their respective projects. Anyone
building a redistributable artifact should regenerate a complete dependency license
inventory as part of that build.

## wx_channels_download

- Project: <https://github.com/ltaoo/wx_channels_download>
- Copyright: Copyright (c) 2025 ltaoo
- License: MIT License with Commons Clause License Condition v1.0

The Commons Clause includes a restriction that does not grant the right to sell the
software. This project integrates with a downloader installed by the user through a local
HTTP API; it does not distribute the downloader binary or root certificate.

`integrations/wechat-channels/wx_channels_download-macos-long-poll.patch` is a compatibility
patch for a specific upstream version. It remains subject to the upstream license and
copyright notices and is not covered by this project's Apache-2.0 license.
