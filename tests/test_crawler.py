import unittest
import asyncio
import http.server
import threading
import time
from unittest.mock import AsyncMock, Mock, patch
from urllib.parse import urlparse

from browser_automation.crawler import SafeCrawler, parse_and_validate_media_type
from browser_automation.policy import CrawlPolicy
from browser_automation.guard import BaseUrlGuard, UrlValidationResult, FailClosedUrlGuard
from browser_automation.bundle import AccessState, PageType, TriState


class MockTestGuard(BaseUrlGuard):
    def validate_url(self, url: str) -> UrlValidationResult:
        if "forbidden" in url or "localhost" in url or "127.0.0.1" in url or "192.168." in url or "10.0.0." in url:
            return UrlValidationResult(is_safe=False, reason="SSRF/Safety violation")
        return UrlValidationResult(is_safe=True, normalized_url=url)


class LoopbackTestGuard(BaseUrlGuard):
    def validate_url(self, url: str) -> UrlValidationResult:
        if urlparse(url).hostname == "127.0.0.1":
            return UrlValidationResult(is_safe=True, normalized_url=url)
        return UrlValidationResult(is_safe=False, reason="Only the local test server is allowed")


class SafeCrawlerIntegrationTests(unittest.IsolatedAsyncioTestCase):

    def test_strict_content_type_parsing(self):
        """Regression test: verify strict media type validation."""
        self.assertTrue(parse_and_validate_media_type("text/html")[0])
        self.assertTrue(parse_and_validate_media_type("text/html; charset=utf-8")[0])
        self.assertTrue(parse_and_validate_media_type("application/xhtml+xml")[0])
        self.assertFalse(parse_and_validate_media_type("application/json")[0])
        self.assertFalse(parse_and_validate_media_type("application/pdf")[0])
        self.assertFalse(parse_and_validate_media_type("image/png")[0])
        self.assertFalse(parse_and_validate_media_type("text/plain")[0])
        self.assertFalse(parse_and_validate_media_type(None)[0])
        self.assertFalse(parse_and_validate_media_type("")[0])
        self.assertFalse(parse_and_validate_media_type("application/json; note=text/html")[0])

    async def test_crawler_guard_rejection(self):
        policy = CrawlPolicy(respect_robots_txt=False)
        guard = MockTestGuard()
        crawler = SafeCrawler(policy=policy, url_guard=guard)

        bundle = await crawler.crawl_site("https://forbidden-site.com")
        self.assertEqual(len(bundle.records), 0)
        self.assertEqual(len(bundle.manifest.failed_urls), 1)
        self.assertIn("Safety violation", bundle.manifest.failed_urls[0]["error"])

    async def test_crawler_max_pages_one(self):
        """Regression test: verify crawler respects max_pages=1 (homepage only)."""
        policy = CrawlPolicy(
            max_pages=1,
            respect_robots_txt=False,
            polite_delay_seconds=0.0,
        )
        guard = MockTestGuard()
        crawler = SafeCrawler(policy=policy, url_guard=guard)

        bundle = await crawler.crawl_site("https://example.com")
        self.assertLessEqual(len(bundle.records), 1)

    async def test_crawler_unsupported_content_type_rejected(self):
        """Regression test: verify non-HTML response (e.g. JSON) is rejected."""
        policy = CrawlPolicy(respect_robots_txt=False, polite_delay_seconds=0.0)
        guard = MockTestGuard()
        crawler = SafeCrawler(policy=policy, url_guard=guard)

        async with crawler.factory:
            await crawler.factory.create_context()
            page = await crawler.factory.create_page()
            async def json_handler(route):
                await route.fulfill(status=200, content_type="application/json", body=b"{}")
            await page.route("**/api/data", json_handler)
            record, _ = await crawler._crawl_single_page(
                page=page,
                target_url="https://example.com/api/data",
                page_type=PageType.HOMEPAGE,
                base_origin="https://example.com",
                total_deadline=time.monotonic() + 30.0,
            )

        self.assertIsNotNone(record.error_message)
        self.assertIn("Unsupported content-type", str(record.error_message))
        self.assertEqual(record.access_state, AccessState.ERROR)

    async def test_crawler_oversized_response_rejected(self):
        """Regression test: verify oversized Content-Length is rejected."""
        policy = CrawlPolicy(
            respect_robots_txt=False,
            max_response_size_bytes=2048,  # 2 KB limit
            polite_delay_seconds=0.0,
        )
        guard = MockTestGuard()
        crawler = SafeCrawler(policy=policy, url_guard=guard)

        async with crawler.factory:
            await crawler.factory.create_context()
            page = await crawler.factory.create_page()
            async def large_handler(route):
                await route.fulfill(
                    status=200,
                    content_type="text/html",
                    headers={"content-length": "100000"},
                    body=b"<html><body>Large</body></html>",
                )
            await page.route("**/large", large_handler)
            record, _ = await crawler._crawl_single_page(
                page=page,
                target_url="https://example.com/large",
                page_type=PageType.HOMEPAGE,
                base_origin="https://example.com",
                total_deadline=time.monotonic() + 30.0,
            )

        self.assertIsNotNone(record.error_message)
        self.assertIn("exceeded maximum", str(record.error_message))

    async def test_post_load_settle_captures_late_rendered_content(self):
        policy = CrawlPolicy(
            respect_robots_txt=False,
            polite_delay_seconds=0.0,
            post_load_settle_seconds=0.2,
        )
        crawler = SafeCrawler(policy=policy, url_guard=MockTestGuard())

        async with crawler.factory:
            await crawler.factory.create_context()
            page = await crawler.factory.create_page()

            async def delayed_content(route):
                await route.fulfill(
                    status=200,
                    content_type="text/html",
                    body=b"""<html><body><main>Store</main><script>
                    setTimeout(() => document.body.insertAdjacentHTML(
                        'beforeend', '<section>Delayed product offer</section>'
                    ), 50);
                    </script></body></html>""",
                )

            await page.route("**/delayed-content", delayed_content)
            record, _ = await crawler._crawl_single_page(
                page=page,
                target_url="https://example.com/delayed-content",
                page_type=PageType.HOMEPAGE,
                base_origin="https://example.com",
                total_deadline=time.monotonic() + 5.0,
            )

        self.assertIn("Delayed product offer", record.rendered_html)
        self.assertEqual(
            record.observation_metadata.extra_signals["page_readiness"]["strategy"],
            "domcontentloaded_bounded_settle",
        )
        self.assertGreaterEqual(
            record.observation_metadata.extra_signals["page_readiness"]["settle_wait_ms"],
            150,
        )

    async def test_post_load_settle_handles_empty_page_content(self):
        policy = CrawlPolicy(
            respect_robots_txt=False,
            polite_delay_seconds=0.0,
            post_load_settle_seconds=0.0,
        )
        crawler = SafeCrawler(policy=policy, url_guard=MockTestGuard())

        async with crawler.factory:
            await crawler.factory.create_context()
            page = await crawler.factory.create_page()

            async def empty_content(route):
                await route.fulfill(status=200, content_type="text/html", body=b"")

            await page.route("**/empty-content", empty_content)
            record, _ = await crawler._crawl_single_page(
                page=page,
                target_url="https://example.com/empty-content",
                page_type=PageType.HOMEPAGE,
                base_origin="https://example.com",
                total_deadline=time.monotonic() + 5.0,
            )

        self.assertEqual(record.access_state, AccessState.UNAVAILABLE)
        self.assertIsNone(record.error_message)

    async def test_post_load_settle_respects_total_deadline(self):
        policy = CrawlPolicy(
            respect_robots_txt=False,
            polite_delay_seconds=0.0,
            post_load_settle_seconds=0.5,
        )
        crawler = SafeCrawler(policy=policy, url_guard=MockTestGuard())

        async with crawler.factory:
            await crawler.factory.create_context()
            page = await crawler.factory.create_page()

            async def quick_page(route):
                await route.fulfill(
                    status=200,
                    content_type="text/html",
                    body=b"<html><body><main>Store</main></body></html>",
                )

            await page.route("**/settle-deadline", quick_page)
            start = time.monotonic()
            record, _ = await crawler._crawl_single_page(
                page=page,
                target_url="https://example.com/settle-deadline",
                page_type=PageType.HOMEPAGE,
                base_origin="https://example.com",
                total_deadline=start + 0.15,
            )

        self.assertLess(time.monotonic() - start, 1.0)
        self.assertEqual(record.access_state, AccessState.UNAVAILABLE)
        self.assertIn("deadline expired", str(record.error_message).lower())

    async def test_crawler_records_late_dom_signal_metadata(self):
        policy = CrawlPolicy(
            respect_robots_txt=False,
            polite_delay_seconds=0.0,
            post_load_settle_seconds=0.0,
            max_scroll_attempts=1,
        )
        crawler = SafeCrawler(policy=policy, url_guard=MockTestGuard())

        async with crawler.factory:
            await crawler.factory.create_context()
            page = await crawler.factory.create_page()

            async def delayed_popup(route):
                await route.fulfill(
                    status=200,
                    content_type="text/html",
                    body=b"""<html><body>
                    <main>Store content</main><div style="height: 2000px"></div>
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
                    </script></body></html>""",
                )

            await page.route("**/late-popup", delayed_popup)
            record, _ = await crawler._crawl_single_page(
                page=page,
                target_url="https://example.com/late-popup",
                page_type=PageType.HOMEPAGE,
                base_origin="https://example.com",
                total_deadline=time.monotonic() + 5.0,
            )

        self.assertEqual(
            record.observation_metadata.extra_signals["scroll_observation"]["signals"][
                "promotional_popup"
            ],
            "observed_after_scroll",
        )

    async def test_redirect_to_private_ip_aborted(self):
        """Regression test: verify redirect to private IP / localhost is intercepted and aborted."""
        policy = CrawlPolicy(respect_robots_txt=False, polite_delay_seconds=0.0)
        guard = MockTestGuard()
        crawler = SafeCrawler(policy=policy, url_guard=guard)

        async with crawler.factory:
            await crawler.factory.create_context()
            page = await crawler.factory.create_page()
            async def redirect_handler(route):
                await route.fulfill(
                    status=302,
                    headers={"location": "http://127.0.0.1/admin"},
                )
            await page.route("**/redirect-private", redirect_handler)
            record, _ = await crawler._crawl_single_page(
                page=page,
                target_url="https://example.com/redirect-private",
                page_type=PageType.HOMEPAGE,
                base_origin="https://example.com",
                total_deadline=time.monotonic() + 30.0,
            )

        self.assertIsNotNone(record.error_message)

    async def test_subresource_private_ip_aborted(self):
        """Regression test: verify SSRF protection on subresource (e.g. image pointing to 192.168.1.1)."""
        policy = CrawlPolicy(respect_robots_txt=False, polite_delay_seconds=0.0)
        guard = MockTestGuard()
        crawler = SafeCrawler(policy=policy, url_guard=guard)

        async with crawler.factory:
            await crawler.factory.create_context()
            page = await crawler.factory.create_page()

            async def page_handler(route):
                await route.fulfill(
                    status=200,
                    content_type="text/html",
                    body=b"""
                    <!DOCTYPE html>
                    <html>
                    <head><title>Test Store</title></head>
                    <body>
                        <main>
                            <h1>Welcome to Store</h1>
                            <p>Legitimate products and services for customers.</p>
                            <img src="http://192.168.1.1/internal-leak.png" />
                        </main>
                    </body>
                    </html>
                    """
                )
            await page.route("**/subresource-test", page_handler)
            record, _ = await crawler._crawl_single_page(
                page=page,
                target_url="https://example.com/subresource-test",
                page_type=PageType.HOMEPAGE,
                base_origin="https://example.com",
                total_deadline=time.monotonic() + 30.0,
            )

        # Main page renders content, image request to private IP was aborted by route handler
        self.assertEqual(record.access_state, AccessState.ACCESSIBLE)

    async def test_legitimate_cdn_subresource_allowed(self):
        """Regression test: verify legitimate cross-origin CDN subresource passes SSRF guard."""
        policy = CrawlPolicy(respect_robots_txt=False, polite_delay_seconds=0.0)
        guard = MockTestGuard()
        crawler = SafeCrawler(policy=policy, url_guard=guard)

        async with crawler.factory:
            await crawler.factory.create_context()
            page = await crawler.factory.create_page()

            async def page_handler(route):
                await route.fulfill(
                    status=200,
                    content_type="text/html",
                    body=b"""
                    <!DOCTYPE html>
                    <html>
                    <head><title>CDN Test</title></head>
                    <body>
                        <main>
                            <h1>CDN Test Page</h1>
                            <script src="https://cdn.example.org/bundle.js"></script>
                        </main>
                    </body>
                    </html>
                    """
                )
            async def cdn_handler(route):
                await route.fulfill(
                    status=200,
                    content_type="application/javascript",
                    body=b"console.log('CDN loaded');",
                )

            await page.route("**/cdn-test", page_handler)
            await page.route("https://cdn.example.org/*", cdn_handler)

            record, _ = await crawler._crawl_single_page(
                page=page,
                target_url="https://example.com/cdn-test",
                page_type=PageType.HOMEPAGE,
                base_origin="https://example.com",
                total_deadline=time.monotonic() + 30.0,
            )

        self.assertEqual(record.access_state, AccessState.ACCESSIBLE)
        self.assertTrue(any("cdn.example.org" in s for s in record.script_urls))

    async def test_deadline_expired_during_dom_inspection_terminates_crawl(self):
        """Regression test: verify deadline expiring during DOM inspection terminates and cleans up."""
        policy = CrawlPolicy(
            respect_robots_txt=False,
            max_total_duration_seconds=1.0,
            polite_delay_seconds=0.0,
        )
        guard = MockTestGuard()
        crawler = SafeCrawler(policy=policy, url_guard=guard)

        async with crawler.factory:
            await crawler.factory.create_context()
            page = await crawler.factory.create_page()

            async def slow_page_handler(route):
                await route.fulfill(
                    status=200,
                    content_type="text/html",
                    body=b"<html><body><h1>Fast HTML</h1></body></html>",
                )
            await page.route("**/slow-dom", slow_page_handler)

            # Patch inspect_page_dom to simulate a delay that exceeds deadline
            with patch("browser_automation.crawler.inspect_page_dom") as mock_inspect:
                async def slow_inspect(*args, **kwargs):
                    await asyncio.sleep(2.0)
                    return TriState.OBSERVED, []
                mock_inspect.side_effect = slow_inspect

                start = time.monotonic()
                record, _ = await crawler._crawl_single_page(
                    page=page,
                    target_url="https://example.com/slow-dom",
                    page_type=PageType.HOMEPAGE,
                    base_origin="https://example.com",
                    total_deadline=start + 0.2,
                )
                elapsed = time.monotonic() - start

                self.assertLess(elapsed, 1.5)
                self.assertEqual(record.access_state, AccessState.UNAVAILABLE)
                self.assertIn("deadline", str(record.error_message).lower())

    async def test_deadline_exhaustion_stops_crawling(self):
        """Regression test: verify crawl stops when total_deadline is exhausted."""
        policy = CrawlPolicy(
            respect_robots_txt=False,
            max_total_duration_seconds=0.001,  # immediate expiration
            polite_delay_seconds=0.0,
        )
        guard = MockTestGuard()
        crawler = SafeCrawler(policy=policy, url_guard=guard)

        bundle = await crawler.crawl_site("https://example.com")
        self.assertTrue(len(bundle.manifest.failed_urls) > 0 or len(bundle.manifest.skipped_urls) > 0)

    async def test_redirect_chain_recording_order(self):
        """Regression test: verify initial and redirect destinations are recorded in order."""
        policy = CrawlPolicy(respect_robots_txt=False, polite_delay_seconds=0.0)
        guard = MockTestGuard()
        crawler = SafeCrawler(policy=policy, url_guard=guard)

        async with crawler.factory:
            await crawler.factory.create_context()
            page = await crawler.factory.create_page()

            async def r1_handler(route):
                await route.fulfill(status=302, headers={"location": "https://example.com/step2"})
            async def r2_handler(route):
                await route.fulfill(
                    status=200,
                    content_type="text/html",
                    body=b"<html><body><h1>Final Destination</h1></body></html>",
                )

            await page.route("**/step1", r1_handler)
            await page.route("**/step2", r2_handler)

            record, _ = await crawler._crawl_single_page(
                page=page,
                target_url="https://example.com/step1",
                page_type=PageType.HOMEPAGE,
                base_origin="https://example.com",
                total_deadline=time.monotonic() + 30.0,
            )

        self.assertEqual(record.provisional_redirect_chain, ["https://example.com/step1", "https://example.com/step2"])

    async def test_robots_redirect_validation_and_failures(self):
        """Regression test: verify robots redirects to different paths, private IPs, cross-origins, and limits."""
        policy = CrawlPolicy(
            respect_robots_txt=True,
            max_redirects=2,
            polite_delay_seconds=0.0,
        )
        guard = MockTestGuard()
        crawler = SafeCrawler(policy=policy, url_guard=guard)

        async with crawler.factory:
            await crawler.factory.create_context()
            page = await crawler.factory.create_page()

            def make_response(status, headers=None, body=b""):
                mock_response = Mock(status=status, headers=headers or {})
                mock_response.body = AsyncMock(return_value=body)
                mock_response.dispose = AsyncMock()
                return mock_response

            # 1. Parse the content returned after a same-origin path redirect.
            with patch.object(page.request, "get", new_callable=AsyncMock) as request_get:
                request_get.side_effect = [
                    make_response(302, {"location": "https://example.com/custom-robots.txt"}),
                    make_response(
                        200,
                        body=b"User-agent: *\nDisallow: /secret/",
                    ),
                ]
                await crawler.fetch_robots_txt("https://example.com", time.monotonic() + 30.0)

            self.assertEqual(
                [call.args[0] for call in request_get.await_args_list],
                [
                    "https://example.com/robots.txt",
                    "https://example.com/custom-robots.txt",
                ],
            )
            self.assertTrue(all(call.kwargs["max_redirects"] == 0 for call in request_get.await_args_list))

            allowed, _ = crawler.robots_policy.is_allowed("https://example.com/secret/doc")
            self.assertFalse(allowed)

            # 2. Robots redirect to private IP (must be blocked & fail closed)
            with patch.object(page.request, "get", new_callable=AsyncMock) as request_get:
                request_get.return_value = make_response(
                    302, {"location": "http://127.0.0.1/robots.txt"}
                )
                await crawler.fetch_robots_txt(
                    "https://example.com", time.monotonic() + 30.0
                )
                request_get.assert_awaited_once()

            allowed, reason = crawler.robots_policy.is_allowed("https://example.com/products")
            self.assertFalse(allowed)
            self.assertIn("fail-closed policy disallows crawling", reason)

            # 3. Robots redirect to cross-origin (must be blocked & fail closed)
            with patch.object(page.request, "get", new_callable=AsyncMock) as request_get:
                request_get.return_value = make_response(
                    302, {"location": "https://attacker.com/robots.txt"}
                )
                await crawler.fetch_robots_txt(
                    "https://example.com", time.monotonic() + 30.0
                )
                request_get.assert_awaited_once()

            allowed, reason = crawler.robots_policy.is_allowed("https://example.com/products")
            self.assertFalse(allowed)
            self.assertIn("fail-closed policy disallows crawling", reason)

            # 4. Robots redirect limit exceeded
            with patch.object(page.request, "get", new_callable=AsyncMock) as request_get:
                request_get.side_effect = [
                    make_response(302, {"location": "https://example.com/hop1"}),
                    make_response(302, {"location": "https://example.com/hop2"}),
                    make_response(302, {"location": "https://example.com/hop3"}),
                ]
                await crawler.fetch_robots_txt(
                    "https://example.com", time.monotonic() + 30.0
                )
                self.assertEqual(request_get.await_count, 3)

            allowed, reason = crawler.robots_policy.is_allowed("https://example.com/products")
            self.assertFalse(allowed)
            self.assertIn("fail-closed", reason)

    async def test_robots_redirect_fetches_final_content_from_local_server(self):
        class RobotsHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/robots.txt":
                    self.send_response(302)
                    self.send_header("Location", "/custom-robots.txt")
                    self.end_headers()
                elif self.path == "/custom-robots.txt":
                    body = b"User-agent: *\nDisallow: /secret/"
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_error(404)

            def log_message(self, format, *args):
                return

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), RobotsHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        try:
            crawler = SafeCrawler(
                policy=CrawlPolicy(polite_delay_seconds=0.0),
                url_guard=LoopbackTestGuard(),
            )
            async with crawler.factory:
                await crawler.factory.create_context()
                await crawler.factory.create_page()
                base_url = f"http://127.0.0.1:{server.server_port}"
                await crawler.fetch_robots_txt(base_url, time.monotonic() + 10.0)

            allowed, _ = crawler.robots_policy.is_allowed(f"{base_url}/secret/doc")
            self.assertFalse(allowed)
        finally:
            server.shutdown()
            server.server_close()
            server_thread.join(timeout=2.0)

    async def test_robots_fetch_failures_and_response_limits_fail_closed(self):
        policy = CrawlPolicy(
            max_response_size_bytes=1024,
            polite_delay_seconds=0.0,
        )
        crawler = SafeCrawler(policy=policy, url_guard=MockTestGuard())

        def make_response(status, headers=None, body=b""):
            mock_response = Mock(status=status, headers=headers or {})
            mock_response.body = AsyncMock(return_value=body)
            mock_response.dispose = AsyncMock()
            return mock_response

        async with crawler.factory:
            await crawler.factory.create_context()
            page = await crawler.factory.create_page()

            with patch.object(page.request, "get", new_callable=AsyncMock) as request_get:
                request_get.side_effect = RuntimeError("request failed")
                await crawler.fetch_robots_txt("https://example.com", time.monotonic() + 30.0)
            allowed, reason = crawler.robots_policy.is_allowed(
                "https://example.com/products"
            )
            self.assertFalse(allowed)
            self.assertIn("request failed", reason)

            with patch.object(page.request, "get", new_callable=AsyncMock) as request_get:
                request_get.return_value = make_response(
                    200, {"content-length": "2048"}
                )
                await crawler.fetch_robots_txt("https://example.com", time.monotonic() + 30.0)
            allowed, reason = crawler.robots_policy.is_allowed(
                "https://example.com/products"
            )
            self.assertFalse(allowed)
            self.assertIn("Content-Length", reason)

            with patch.object(page.request, "get", new_callable=AsyncMock) as request_get:
                request_get.return_value = make_response(200, body=b"x" * 1025)
                await crawler.fetch_robots_txt("https://example.com", time.monotonic() + 30.0)
            allowed, reason = crawler.robots_policy.is_allowed(
                "https://example.com/products"
            )
            self.assertFalse(allowed)
            self.assertIn("body size", reason)


if __name__ == "__main__":
    unittest.main()
