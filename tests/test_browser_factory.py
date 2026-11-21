import unittest
import asyncio
from unittest.mock import patch, AsyncMock

from browser_automation.config import BrowserLaunchConfig, BrowserContextConfig
from browser_automation.factory import BrowserFactory


class BrowserFactoryLifecycleTests(unittest.IsolatedAsyncioTestCase):

    async def test_browser_launch_and_cleanup(self):
        factory = BrowserFactory()

        async with factory:
            self.assertIsNotNone(factory.playwright)
            self.assertIsNotNone(factory.browser)

            await factory.create_context()
            page = await factory.create_page()

            await page.set_content(
                "<html><head><title>Lifecycle Test</title></head></html>"
            )

            self.assertEqual(await page.title(), "Lifecycle Test")
            browser_reference = factory.browser

        self.assertTrue(page.is_closed())
        self.assertFalse(browser_reference.is_connected())
        self.assertIsNone(factory.page)
        self.assertIsNone(factory.context)
        self.assertIsNone(factory.browser)
        self.assertIsNone(factory.playwright)

    async def test_cleanup_after_exception(self):
        factory = BrowserFactory()
        browser_reference = None

        with self.assertRaisesRegex(RuntimeError, "Simulated crawl failure"):
            async with factory:
                await factory.create_context()
                await factory.create_page()
                browser_reference = factory.browser
                raise RuntimeError("Simulated crawl failure")

        self.assertFalse(browser_reference.is_connected())
        self.assertIsNone(factory.page)
        self.assertIsNone(factory.context)
        self.assertIsNone(factory.browser)
        self.assertIsNone(factory.playwright)

    async def test_repeated_browser_sessions(self):
        browser_references = []

        for _ in range(3):
            factory = BrowserFactory()
            async with factory:
                await factory.create_context()
                await factory.create_page()
                browser_references.append(factory.browser)

        for browser in browser_references:
            self.assertFalse(browser.is_connected())

    async def test_duplicate_context_is_rejected(self):
        factory = BrowserFactory()
        async with factory:
            await factory.create_context()
            with self.assertRaisesRegex(RuntimeError, "context already exists"):
                await factory.create_context()

    async def test_duplicate_page_is_rejected(self):
        factory = BrowserFactory()
        async with factory:
            await factory.create_context()
            await factory.create_page()
            with self.assertRaisesRegex(RuntimeError, "page already exists"):
                await factory.create_page()

    async def test_context_configuration(self):
        config = BrowserContextConfig(
            viewport_width=1280,
            viewport_height=720,
            locale="en-GB",
            ignore_https_errors=True,
            user_agent="CustomAgent/1.0",
        )
        factory = BrowserFactory(context_config=config)

        async with factory:
            context = await factory.create_context()
            page = await factory.create_page()
            self.assertEqual(page.viewport_size["width"], 1280)
            self.assertEqual(page.viewport_size["height"], 720)

    async def test_startup_failure_cleans_up_playwright(self):
        """Verify startup failure cleans up playwright safely."""
        factory = BrowserFactory()
        with patch("browser_automation.factory.async_playwright") as mock_pw_init:
            mock_pw_instance = AsyncMock()
            mock_pw_instance.chromium.launch.side_effect = RuntimeError("Chromium launch failed")
            mock_pw_init.return_value.start = AsyncMock(return_value=mock_pw_instance)

            with self.assertRaisesRegex(RuntimeError, "Chromium launch failed"):
                await factory.start()

            mock_pw_instance.stop.assert_awaited_once()
            self.assertIsNone(factory.playwright)
            self.assertIsNone(factory.browser)

    async def test_cleanup_failure_resilience(self):
        """Verify cleanup proceeds to other resources even when an earlier resource close fails."""
        factory = BrowserFactory()
        await factory.start()
        context = await factory.create_context()
        page = await factory.create_page()

        # Mock page.close to throw
        page.close = AsyncMock(side_effect=RuntimeError("Page close exception"))

        # Calling close directly should handle page exception and continue cleaning context/browser
        await factory.close()

        self.assertIsNone(factory.page)
        self.assertIsNone(factory.context)
        self.assertIsNone(factory.browser)
        self.assertIsNone(factory.playwright)

    
    async def test_cancellation_cleans_up_resources(self):
        """Verify asyncio task cancellation leaves no leaked resources."""
        factory = BrowserFactory()
        browser_ref = None
        ready = asyncio.Event()

        async def worker():
            nonlocal browser_ref

            async with factory:
                await factory.create_context()
                await factory.create_page()

                browser_ref = factory.browser
                ready.set()

                await asyncio.sleep(10)

        task = asyncio.create_task(worker())

        try:
            # Wait until browser, context, and page are ready.
            await asyncio.wait_for(ready.wait(), timeout=30)
        except BaseException:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            raise

        # Cancel only after resources have been created.
        task.cancel()

        with self.assertRaises(asyncio.CancelledError):
            await task

        self.assertIsNotNone(browser_ref)
        self.assertFalse(browser_ref.is_connected())
        self.assertIsNone(factory.browser)
        self.assertIsNone(factory.context)
        self.assertIsNone(factory.page)
        self.assertIsNone(factory.playwright)



if __name__ == "__main__":
    unittest.main()
