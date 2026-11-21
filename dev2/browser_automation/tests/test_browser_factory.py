
import unittest

from dev2.browser_automation.browser_factory import BrowserFactory


class BrowserFactoryLifecycleTests(unittest.IsolatedAsyncioTestCase):

    async def test_browser_launch_and_cleanup(self):
        """Verify browser resources are created and closed."""

        factory = BrowserFactory()

        async with factory:
            self.assertIsNotNone(factory.playwright)
            self.assertIsNotNone(factory.browser)

            context = await factory.create_context()
            page = await factory.create_page()

            await page.set_content(
                "<html><head><title>Lifecycle Test</title></head></html>"
            )

            self.assertEqual(
                await page.title(),
                "Lifecycle Test"
            )

            browser_reference = factory.browser

        self.assertTrue(page.is_closed())
        self.assertFalse(browser_reference.is_connected())

        self.assertIsNone(factory.page)
        self.assertIsNone(factory.context)
        self.assertIsNone(factory.browser)
        self.assertIsNone(factory.playwright)

    async def test_cleanup_after_exception(self):
        """Verify resources close even when a crawl fails."""

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
        """Verify repeated sessions close without leaving browsers connected."""

        browser_references = []

        for _ in range(3):
            factory = BrowserFactory()

            async with factory:
                await factory.create_context()
                await factory.create_page()

                browser_references.append(factory.browser)

        for browser in browser_references:
            self.assertFalse(browser.is_connected())


if __name__ == "__main__":
    unittest.main()
