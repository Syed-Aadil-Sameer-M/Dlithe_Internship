import unittest
from browser_automation.factory import BrowserFactory
from browser_automation.inspector import inspect_page_dom
from browser_automation.bundle import TriState


class DynamicDomInspectorTests(unittest.IsolatedAsyncioTestCase):

    async def test_inspect_page_dom_newsletter_and_inputs(self):
        factory = BrowserFactory()
        async with factory:
            await factory.create_context()
            page = await factory.create_page()

            html_content = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Store Test Page</title>
                <script src="https://example.com/static/analytics.js"></script>
                <script src="/static/bundle.js"></script>
            </head>
            <body>
                <h1>Welcome to Store</h1>
                <div class="modal popup" role="dialog" style="display: block;">
                    <h2>Subscribe to our Newsletter</h2>
                    <p>Get 10% off your first order!</p>
                    <form action="/subscribe" method="POST">
                        <label for="email-field">Your Email Address</label>
                        <input type="email" id="email-field" name="email" placeholder="Enter email" />
                        <label for="phone-field">Phone Number</label>
                        <input type="tel" id="phone-field" name="phone" />
                        <button type="submit">Subscribe</button>
                    </form>
                </div>
            </body>
            </html>
            """
            await page.set_content(html_content)

            metadata, script_urls = await inspect_page_dom(page, max_scroll_attempts=1)

            self.assertEqual(metadata.newsletter_form, TriState.OBSERVED)
            self.assertEqual(metadata.email_input, TriState.OBSERVED)
            self.assertEqual(metadata.phone_input, TriState.OBSERVED)
            self.assertEqual(metadata.dialog_modal, TriState.OBSERVED)
            self.assertEqual(metadata.promotional_popup, TriState.OBSERVED)
            self.assertTrue(metadata.has_newsletter_form)
            self.assertTrue(metadata.has_email_input)
            self.assertTrue(metadata.has_phone_input)
            self.assertIn("/subscribe", metadata.observed_form_actions)
            self.assertIn("Your Email Address", metadata.observed_input_labels)

            self.assertTrue(any("analytics.js" in s for s in script_urls))
            self.assertTrue(any("bundle.js" in s for s in script_urls))

    async def test_hidden_newsletter_and_hidden_modal(self):
        """Verify hidden elements are not marked as OBSERVED."""
        factory = BrowserFactory()
        async with factory:
            await factory.create_context()
            page = await factory.create_page()

            html_content = """
            <html>
            <body>
                <div class="modal" style="display: none;">
                    <form action="/newsletter">
                        <input type="email" name="hidden_email" />
                    </form>
                </div>
                <p>Welcome to our standard content</p>
            </body>
            </html>
            """
            await page.set_content(html_content)
            metadata, _ = await inspect_page_dom(page)

            self.assertEqual(metadata.dialog_modal, TriState.NOT_OBSERVED)
            self.assertEqual(metadata.newsletter_form, TriState.NOT_OBSERVED)
            self.assertEqual(metadata.email_input, TriState.NOT_OBSERVED)

    async def test_newsletter_keyword_without_form(self):
        """Verify the mere mention of 'newsletter' in prose does not trigger newsletter form detection."""
        factory = BrowserFactory()
        async with factory:
            await factory.create_context()
            page = await factory.create_page()

            html_content = """
            <html>
            <body>
                <article>
                    <h2>Our History</h2>
                    <p>In our monthly newsletter from 1999, we discussed our origins.</p>
                </article>
            </body>
            </html>
            """
            await page.set_content(html_content)
            metadata, _ = await inspect_page_dom(page)

            self.assertEqual(metadata.newsletter_form, TriState.NOT_OBSERVED)
            self.assertEqual(metadata.email_input, TriState.NOT_OBSERVED)

    async def test_cookie_banner_detection_and_no_dismiss(self):
        """Verify cookie banner is detected without clicking or dismissing it."""
        factory = BrowserFactory()
        async with factory:
            await factory.create_context()
            page = await factory.create_page()

            html_content = """
            <html>
            <body>
                <div id="cookie-consent-banner" class="cookie-notice" style="display: block;">
                    <p>We use cookies to improve your experience.</p>
                    <button id="accept-cookies">Accept All</button>
                    <button id="reject-cookies">Reject</button>
                </div>
            </body>
            </html>
            """
            await page.set_content(html_content)
            metadata, _ = await inspect_page_dom(page)

            self.assertEqual(metadata.cookie_banner, TriState.OBSERVED)

            # Ensure banner still exists and is visible (was not dismissed/clicked)
            is_visible = await page.is_visible("#cookie-consent-banner")
            self.assertTrue(is_visible)

    async def test_scroll_recheck_marks_late_signals(self):
        factory = BrowserFactory()
        async with factory:
            await factory.create_context()
            page = await factory.create_page()
            await page.set_content(
                """
                <html><body>
                    <main>Store content</main>
                    <div style="height: 2000px"></div>
                    <script>
                    window.addEventListener("scroll", () => {
                        setTimeout(() => {
                            const popup = document.createElement("section");
                            popup.setAttribute("role", "dialog");
                            popup.setAttribute("aria-label", "Special offer");
                            popup.textContent = "Save 20% today";
                            document.body.appendChild(popup);
                        }, 25);
                    }, { once: true });
                    </script>
                </body></html>
                """
            )

            metadata, _ = await inspect_page_dom(page, max_scroll_attempts=1)

            self.assertEqual(metadata.dialog_modal, TriState.OBSERVED)
            self.assertEqual(metadata.promotional_popup, TriState.OBSERVED)
            scroll_observation = metadata.extra_signals["scroll_observation"]
            self.assertEqual(scroll_observation["scroll_attempts"], 1)
            self.assertEqual(
                scroll_observation["signals"]["promotional_popup"],
                "observed_after_scroll",
            )

    async def test_semantic_phone_and_promotion_markers_do_not_capture_input_values(self):
        factory = BrowserFactory()
        async with factory:
            await factory.create_context()
            page = await factory.create_page()
            await page.set_content(
                """
                <html><body>
                    <label for="contact">SMS mobile number</label>
                    <input id="contact" type="text" value="sensitive-test-value">
                    <div aria-label="Discount offer">View current promotion</div>
                </body></html>
                """
            )

            metadata, _ = await inspect_page_dom(page, max_scroll_attempts=0)

            self.assertEqual(metadata.phone_input, TriState.OBSERVED)
            self.assertEqual(metadata.promotional_popup, TriState.OBSERVED)
            self.assertIn("SMS mobile number", metadata.observed_input_labels)
            self.assertNotIn("sensitive-test-value", repr(metadata))

    async def test_scroll_attempts_are_capped_and_empty_dom_is_not_observed(self):
        factory = BrowserFactory()
        async with factory:
            await factory.create_context()
            page = await factory.create_page()
            await page.set_content("<html><body></body></html>")

            metadata, _ = await inspect_page_dom(page, max_scroll_attempts=10)

            self.assertEqual(metadata.dialog_modal, TriState.NOT_OBSERVED)
            scroll_observation = metadata.extra_signals["scroll_observation"]
            self.assertEqual(scroll_observation["scroll_attempts"], 2)
            self.assertEqual(scroll_observation["rechecks_completed"], 2)
            self.assertTrue(scroll_observation["window_complete"])
            self.assertEqual(
                scroll_observation["signals"]["dialog_modal"],
                "not_observed_within_window",
            )

    async def test_closed_page_inspection_returns_unknown(self):
        factory = BrowserFactory()
        async with factory:
            await factory.create_context()
            page = await factory.create_page()
            await page.close()

            metadata, _ = await inspect_page_dom(page, max_scroll_attempts=1)

            self.assertEqual(metadata.dialog_modal, TriState.UNKNOWN)
            self.assertFalse(metadata.extra_signals["scroll_observation"]["window_complete"])
            self.assertEqual(
                metadata.extra_signals["scroll_observation"]["signals"]["dialog_modal"],
                "unknown",
            )


if __name__ == "__main__":
    unittest.main()
