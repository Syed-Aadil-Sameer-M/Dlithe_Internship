
"""
Reusable Playwright browser lifecycle management.

This module is responsible only for creating and cleaning up
Playwright resources. It does not perform crawling or extraction.
"""

from dataclasses import dataclass

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    Playwright,
)


@dataclass(frozen=True)
class BrowserConfig:
    """Configuration for launching and configuring a browser."""

    headless: bool = True
    navigation_timeout_ms: int = 30_000
    default_timeout_ms: int = 10_000
    viewport_width: int = 1366
    viewport_height: int = 768


class BrowserFactory:
    """Creates and manages Playwright browser resources."""

    def __init__(self, config: BrowserConfig | None = None):
        self.config = config or BrowserConfig()

        self.playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    async def start(self) -> None:
        """Start Playwright and launch Chromium."""

        self.playwright = await async_playwright().start()

        try:
            self.browser = await self.playwright.chromium.launch(
                headless=self.config.headless
            )
        except BaseException:
            await self.playwright.stop()
            self.playwright = None
            raise

    async def create_context(self) -> BrowserContext:
        """Create an isolated browser context."""

        if self.browser is None:
            raise RuntimeError("Browser has not been started.")

        self.context = await self.browser.new_context(
            viewport={
                "width": self.config.viewport_width,
                "height": self.config.viewport_height,
            }
        )

        self.context.set_default_timeout(
            self.config.default_timeout_ms
        )

        self.context.set_default_navigation_timeout(
            self.config.navigation_timeout_ms
        )

        return self.context

    async def create_page(self) -> Page:
        """Create a new page inside the current context."""

        if self.context is None:
            raise RuntimeError("Browser context has not been created.")

        self.page = await self.context.new_page()
        return self.page

    async def close(self) -> None:
        """Close resources in reverse order, even if cleanup fails."""

        try:
            if self.page is not None:
                await self.page.close()
        finally:
            self.page = None

            try:
                if self.context is not None:
                    await self.context.close()
            finally:
                self.context = None

                try:
                    if self.browser is not None:
                        await self.browser.close()
                finally:
                    self.browser = None

                    try:
                        if self.playwright is not None:
                            await self.playwright.stop()
                    finally:
                        self.playwright = None

    async def __aenter__(self):
        """Allow usage with Python's async with statement."""

        try:
            await self.start()
            return self
        except BaseException:
            await self.close()
            raise

    async def __aexit__(self, exc_type, exc_value, traceback):
        """Guarantee cleanup when the async with block exits."""

        await self.close()
        return False
