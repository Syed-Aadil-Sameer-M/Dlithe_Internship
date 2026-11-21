import unittest
from browser_automation.robots import RobotsPolicy
from browser_automation.policy import CrawlPolicy, normalize_url, get_origin
from browser_automation.guard import FailClosedUrlGuard, BaseUrlGuard, UrlValidationResult
from browser_automation.exceptions import (
    PolicyViolationError,
    UrlGuardError,
    RobotsDisallowedError,
)


class MockSafeUrlGuard(BaseUrlGuard):
    def __init__(self, allowed_domains: list[str]):
        self.allowed_domains = allowed_domains

    def validate_url(self, url: str) -> UrlValidationResult:
        for d in self.allowed_domains:
            if d in url:
                return UrlValidationResult(is_safe=True, reason="Allowed domain", normalized_url=url)
        return UrlValidationResult(is_safe=False, reason="Untrusted domain")


class SafeCrawlPolicyTests(unittest.TestCase):

    def test_robots_txt_allow_and_disallow(self):
        robots_content = """
User-agent: *
Disallow: /admin/
Disallow: /checkout/
Allow: /products/

User-agent: BadBot
Disallow: /
"""
        rp = RobotsPolicy(user_agent="DLitheEcommerceBot/1.0")
        rp.parse_robots_txt_content("https://example.com", robots_content)

        # /admin/ disallowed
        allowed, reason = rp.is_allowed("https://example.com/admin/settings")
        self.assertFalse(allowed)
        self.assertIn("Disallowed by robots.txt", reason)

        # /products/ allowed
        allowed, reason = rp.is_allowed("https://example.com/products/item-1")
        self.assertTrue(allowed)

    def test_user_agent_rule_evaluation(self):
        robots_content = """
User-agent: DLitheEcommerceBot
Disallow: /private/

User-agent: *
Disallow: /admin/
"""
        rp = RobotsPolicy(user_agent="DLitheEcommerceBot/1.0")
        rp.parse_robots_txt_content("https://example.com", robots_content)

        allowed, _ = rp.is_allowed("https://example.com/private/doc")
        self.assertFalse(allowed)

    def test_robots_txt_retrieval_failure_policy(self):
        # Test fail-closed behavior
        rp_fail_closed = RobotsPolicy(user_agent="DLitheEcommerceBot", fail_closed_on_error=True)
        rp_fail_closed.record_fetch_failure("https://example.com", "Connection timed out")

        allowed, reason = rp_fail_closed.is_allowed("https://example.com/products")
        self.assertFalse(allowed)
        self.assertIn("fail-closed policy disallows crawling", reason)

        # Test lenient behavior
        rp_lenient = RobotsPolicy(user_agent="DLitheEcommerceBot", fail_closed_on_error=False)
        rp_lenient.record_fetch_failure("https://example.com", "Connection timed out")
        allowed, reason = rp_lenient.is_allowed("https://example.com/products")
        self.assertTrue(allowed)

    def test_same_site_policy(self):
        policy = CrawlPolicy(same_site_only=True)
        guard = MockSafeUrlGuard(allowed_domains=["example.com"])

        # Same origin allowed
        norm = policy.enforce_navigation_policy(
            target_url="https://example.com/products",
            base_origin="https://example.com",
            url_guard=guard,
        )
        self.assertEqual(norm, "https://example.com/products")

        # Different scheme rejected
        with self.assertRaises(PolicyViolationError):
            policy.enforce_navigation_policy(
                target_url="http://example.com/products",
                base_origin="https://example.com",
                url_guard=guard,
            )

        # Different host rejected
        with self.assertRaises(PolicyViolationError):
            policy.enforce_navigation_policy(
                target_url="https://attacker.com/products",
                base_origin="https://example.com",
                url_guard=guard,
            )

        # Different port rejected
        with self.assertRaises(PolicyViolationError):
            policy.enforce_navigation_policy(
                target_url="https://example.com:8443/products",
                base_origin="https://example.com",
                url_guard=guard,
            )

    def test_url_guard_fail_closed(self):
        policy = CrawlPolicy()
        fail_closed_guard = FailClosedUrlGuard()

        with self.assertRaises(UrlGuardError):
            policy.enforce_navigation_policy(
                target_url="https://example.com",
                base_origin="https://example.com",
                url_guard=fail_closed_guard,
            )

        with self.assertRaises(UrlGuardError):
            policy.enforce_navigation_policy(
                target_url="https://example.com",
                base_origin="https://example.com",
                url_guard=None,
            )

    def test_url_guard_rejects_localhost_and_private_ip(self):
        """Regression test: verify guard rejects localhost and private/link-local IPs."""
        guard = FailClosedUrlGuard(allow_all=False)
        for host in ["http://localhost:8000", "https://127.0.0.1/admin", "http://192.168.1.1", "http://10.0.0.1", "http://169.254.169.254"]:
            res = guard.validate_url(host)
            self.assertFalse(res.is_safe)
            self.assertIn("localhost/private/link-local", res.reason)

    def test_url_guard_hostname_parsing_and_ipv6_and_credentials(self):
        """Regression test for robust hostname parsing: IPv6, userinfo, ports, trailing dots, malformed."""
        guard_strict = FailClosedUrlGuard(allow_all=False)
        guard_allow_all = FailClosedUrlGuard(allow_all=True)

        # 1. http://127.0.0.1:8080
        res = guard_strict.validate_url("http://127.0.0.1:8080")
        self.assertFalse(res.is_safe)
        self.assertIn("localhost/private", res.reason)

        # 2. http://[::1]:8080
        res = guard_strict.validate_url("http://[::1]:8080")
        self.assertFalse(res.is_safe)
        self.assertIn("localhost/private", res.reason)

        # 3. http://user@127.0.0.1:8080 (userinfo preceding IP)
        res = guard_strict.validate_url("http://user@127.0.0.1:8080")
        self.assertFalse(res.is_safe)
        self.assertIn("localhost/private", res.reason)

        # 4. http://localhost
        res = guard_strict.validate_url("http://localhost")
        self.assertFalse(res.is_safe)

        # 5. http://192.168.1.1
        res = guard_strict.validate_url("http://192.168.1.1")
        self.assertFalse(res.is_safe)

        # 6. Private destination rejected even with allow_all=True
        self.assertFalse(guard_allow_all.validate_url("http://127.0.0.1:8080").is_safe)
        self.assertFalse(guard_allow_all.validate_url("http://[::1]:8080").is_safe)
        self.assertFalse(guard_allow_all.validate_url("http://user@127.0.0.1:8080").is_safe)
        self.assertFalse(guard_allow_all.validate_url("http://192.168.1.1").is_safe)
        self.assertFalse(guard_allow_all.validate_url("http://localhost").is_safe)

        # 7. Malformed URLs and missing hostnames
        self.assertFalse(guard_strict.validate_url("").is_safe)
        self.assertFalse(guard_strict.validate_url("not a url").is_safe)
        self.assertFalse(guard_strict.validate_url("http://").is_safe)
        self.assertFalse(guard_strict.validate_url("ftp://example.com").is_safe)
        self.assertFalse(guard_strict.validate_url("javascript:alert(1)").is_safe)

        # 8. Legitimate public URLs under allow_all=True or allowed_hosts
        self.assertTrue(guard_allow_all.validate_url("https://example.com").is_safe)
        self.assertTrue(guard_allow_all.validate_url("https://cdn.example.org/bundle.js").is_safe)

        guard_allowed_hosts = FailClosedUrlGuard(allowed_hosts={"example.com"})
        self.assertTrue(guard_allowed_hosts.validate_url("https://example.com/shop").is_safe)
        self.assertTrue(guard_allowed_hosts.validate_url("https://example.com.:443/shop").is_safe)  # trailing dot
        self.assertFalse(guard_allowed_hosts.validate_url("https://other.com").is_safe)

    def test_polite_delay_and_timeout_config(self):
        policy = CrawlPolicy(
            polite_delay_seconds=2.5,
            page_timeout_seconds=45.0,
            max_pages=5,
            max_total_duration_seconds=120.0,
            post_load_settle_seconds=0.5,
            max_redirects=3,
            max_response_size_bytes=1024 * 1024,
            max_scroll_attempts=1,
        )
        self.assertEqual(policy.polite_delay_seconds, 2.5)
        self.assertEqual(policy.page_timeout_seconds, 45.0)
        self.assertEqual(policy.max_pages, 5)
        self.assertEqual(policy.max_total_duration_seconds, 120.0)
        self.assertEqual(policy.post_load_settle_seconds, 0.5)
        self.assertEqual(policy.max_redirects, 3)
        self.assertEqual(policy.max_response_size_bytes, 1024 * 1024)
        self.assertEqual(policy.max_scroll_attempts, 1)

    def test_invalid_policy_configuration_rejected(self):
        """Regression test: verify constructor rejects invalid policy values."""
        with self.assertRaises(ValueError):
            CrawlPolicy(max_pages=0)
        with self.assertRaises(ValueError):
            CrawlPolicy(polite_delay_seconds=-1.0)
        with self.assertRaises(ValueError):
            CrawlPolicy(page_timeout_seconds=-5.0)
        with self.assertRaises(ValueError):
            CrawlPolicy(max_total_duration_seconds=0)
        with self.assertRaises(ValueError):
            CrawlPolicy(post_load_settle_seconds=-0.1)
        with self.assertRaises(ValueError):
            CrawlPolicy(post_load_settle_seconds=float("nan"))
        with self.assertRaises(ValueError):
            CrawlPolicy(max_redirects=-1)
        with self.assertRaises(ValueError):
            CrawlPolicy(max_response_size_bytes=500)

        # Scroll attempts clamped to 2
        p = CrawlPolicy(max_scroll_attempts=5)
        self.assertEqual(p.max_scroll_attempts, 2)
        self.assertEqual(CrawlPolicy(post_load_settle_seconds=5).post_load_settle_seconds, 2.0)

    def test_canonical_url_normalization(self):
        url_with_tracking = "https://EXAMPLE.com:443/products/shoes/?utm_source=google&gclid=123&size=M#reviews"
        normalized = normalize_url(url_with_tracking)
        self.assertEqual(normalized, "https://example.com/products/shoes?size=M")


if __name__ == "__main__":
    unittest.main()
