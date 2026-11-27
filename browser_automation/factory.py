"""
Reusable Playwright browser lifecycle management.

This module manages browser startup, context creation, page creation,
and guaranteed cleanup. It does not perform crawling or extraction.
"""

from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    Playwright,
)

from browser_automation.config import (
    BrowserLaunchConfig,
    BrowserContextConfig,
)
from browser_automation.logging import logger


class BrowserFactory:
    """Creates and manages Playwright browser resources."""

    def __init__(
        self,
        launch_config: BrowserLaunchConfig | None = None,
        context_config: BrowserContextConfig | None = None,
    ):
        self.launch_config = launch_config or BrowserLaunchConfig()
        self.context_config = context_config or BrowserContextConfig()

        self.playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    async def start(self) -> None:
        """Start Playwright and launch Chromium."""
        if self.playwright is not None:
            raise RuntimeError("Browser factory has already been started.")

        logger.debug("Starting Playwright and launching Chromium.")
        self.playwright = await async_playwright().start()

        try:
            self.browser = await self.playwright.chromium.launch(
                headless=self.launch_config.headless,
                slow_mo=self.launch_config.slow_mo_ms,
            )
        except BaseException:
            logger.exception("Failed to launch browser. Cleaning up Playwright.")
            try:
                await self.playwright.stop()
            except Exception as e:
                logger.warning(f"Error stopping playwright on launch failure: {e}")
            finally:
                self.playwright = None
            raise

    async def create_context(self) -> BrowserContext:
        """Create an isolated browser context."""
        if self.browser is None:
            raise RuntimeError("Browser has not been started.")

        if self.context is not None:
            raise RuntimeError("A browser context already exists.")

        context_kwargs = {
            "viewport": {
                "width": self.context_config.viewport_width,
                "height": self.context_config.viewport_height,
            },
            "locale": self.context_config.locale,
            "ignore_https_errors": self.context_config.ignore_https_errors,
        }
        if self.context_config.user_agent:
            context_kwargs["user_agent"] = self.context_config.user_agent

        self.context = await self.browser.new_context(**context_kwargs)
        self.context.set_default_navigation_timeout(self.context_config.navigation_timeout_ms)
        self.context.set_default_timeout(self.context_config.default_timeout_ms)

        return self.context

    async def create_page(self) -> Page:
        """Create a page inside the current browser context."""
        if self.context is None:
            raise RuntimeError("Browser context has not been created.")

        if self.page is not None:
            raise RuntimeError("A page already exists.")

        self.page = await self.context.new_page()
        return self.page

    async def close(self) -> None:
        """Close all resources in reverse creation order, continuing even if an error occurs."""
        errors: list[BaseException] = []

        try:
            if self.page is not None:
                await self.page.close()
        except BaseException as e:
            errors.append(e)
            logger.warning(f"Error while closing page: {e}")
        finally:
            self.page = None

            try:
                if self.context is not None:
                    await self.context.close()
            except BaseException as e:
                errors.append(e)
                logger.warning(f"Error while closing context: {e}")
            finally:
                self.context = None

                try:
                    if self.browser is not None:
                        await self.browser.close()
                except BaseException as e:
                    errors.append(e)
                    logger.warning(f"Error while closing browser: {e}")
                finally:
                    self.browser = None

                    try:
                        if self.playwright is not None:
                            await self.playwright.stop()
                    except BaseException as e:
                        errors.append(e)
                        logger.warning(f"Error while stopping Playwright: {e}")
                    finally:
                        self.playwright = None

        if errors:
            logger.debug(f"Closed resources with {len(errors)} non-fatal cleanup exception(s).")

    async def __aenter__(self) -> "BrowserFactory":
        """Start resources when entering an async with block."""
        try:
            await self.start()
            return self
        except BaseException:
            await self.close()
            raise

    async def __aexit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> bool:
        """Guarantee cleanup when leaving an async with block."""
        await self.close()
        return False
