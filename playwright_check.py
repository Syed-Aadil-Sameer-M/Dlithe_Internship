
import asyncio
import sys

from playwright.async_api import async_playwright


async def main():
    print("Python version:", sys.version)
    print("Starting Playwright...")

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        print("Chromium launched successfully.")

        try:
            context = await browser.new_context()
            page = await context.new_page()

            response = await page.goto(
                "https://example.com",
                wait_until="domcontentloaded",
                timeout=15000,
            )

            print("Browser:", browser.browser_type.name)
            print("HTTP status:", response.status if response else None)
            print("Page title:", await page.title())

            await page.close()
            await context.close()
            print("Page and context closed successfully.")

        finally:
            await browser.close()
            print("Browser closed successfully.")


if __name__ == "__main__":
    asyncio.run(main())
