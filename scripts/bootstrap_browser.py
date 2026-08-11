from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright


async def main() -> None:
    parser = argparse.ArgumentParser(description="创建供 X/微信复用的 Playwright 登录目录")
    parser.add_argument("--profile", type=Path, default=Path("./data/browser-profile"))
    parser.add_argument("--url", default="https://channels.weixin.qq.com/")
    args = parser.parse_args()
    args.profile.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            str(args.profile.resolve()), headless=False
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(args.url)
        print(f"请在浏览器中完成登录。完成后回到终端按 Enter，登录态将保存在 {args.profile}")
        await asyncio.to_thread(input)
        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
