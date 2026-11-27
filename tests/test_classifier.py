import unittest
from browser_automation.classifier import classify_access_state
from browser_automation.bundle import AccessState


class AccessClassificationTests(unittest.TestCase):

    def test_accessible_page(self):
        state, reason = classify_access_state(
            http_status=200,
            rendered_html="<html><body><main><h1>Welcome to Our Store</h1><p>Check out our products.</p></main></body></html>",
            visible_text="Welcome to Our Store Check out our products.",
            final_url="https://example.com",
        )
        self.assertEqual(state, AccessState.ACCESSIBLE)

    def test_http_denial_403_and_401(self):
        state, reason = classify_access_state(
            http_status=403,
            rendered_html="<html><body><h1>Forbidden</h1></body></html>",
            visible_text="Forbidden",
        )
        self.assertEqual(state, AccessState.BLOCKED)
        self.assertIn("403", reason)

        state, _ = classify_access_state(
            http_status=401,
            rendered_html="",
            visible_text="",
        )
        self.assertEqual(state, AccessState.BLOCKED)

    def test_http_rate_limited_429(self):
        state, reason = classify_access_state(
            http_status=429,
            rendered_html="<html><body>Too Many Requests</body></html>",
            visible_text="Too Many Requests",
        )
        self.assertEqual(state, AccessState.BLOCKED)
        self.assertIn("429", reason)

    def test_captcha_and_bot_wall_detection(self):
        # Cloudflare turnstile
        state, _ = classify_access_state(
            http_status=200,
            rendered_html="<html><body><div class='cf-turnstile'></div><p>Verify you are human</p></body></html>",
            visible_text="Verify you are human",
        )
        self.assertEqual(state, AccessState.BLOCKED)

        # Datadome
        state, _ = classify_access_state(
            http_status=200,
            rendered_html="<html><body><script src='https://js.datadome.co/tags.js'></script></body></html>",
            visible_text="Please wait...",
        )
        self.assertEqual(state, AccessState.BLOCKED)

    def test_login_redirect_detection(self):
        state, reason = classify_access_state(
            http_status=200,
            rendered_html="<html><body><h1>Sign in</h1></body></html>",
            visible_text="Sign in to your account",
            final_url="https://example.com/account/login",
        )
        self.assertEqual(state, AccessState.BLOCKED)
        self.assertIn("login endpoint", reason)

    def test_empty_render(self):
        # Empty HTML
        state, reason = classify_access_state(
            http_status=200,
            rendered_html="",
            visible_text="",
        )
        self.assertEqual(state, AccessState.UNAVAILABLE)
        self.assertIn("Empty render", reason)

        # Blank body
        state, reason = classify_access_state(
            http_status=200,
            rendered_html="<html><head></head><body></body></html>",
            visible_text="",
        )
        self.assertEqual(state, AccessState.UNAVAILABLE)
        self.assertIn("Empty render", reason)

    def test_network_timeout_and_errors(self):
        # Timeout error
        state, reason = classify_access_state(
            http_status=None,
            rendered_html="",
            visible_text="",
            error=TimeoutError("Navigation timeout of 30000ms exceeded"),
        )
        self.assertEqual(state, AccessState.UNAVAILABLE)
        self.assertIn("timed out", reason)

        # Server error 500
        state, reason = classify_access_state(
            http_status=500,
            rendered_html="<html><body>Server Error</body></html>",
            visible_text="500 Internal Server Error",
        )
        self.assertEqual(state, AccessState.UNAVAILABLE)
        self.assertIn("500", reason)


if __name__ == "__main__":
    unittest.main()
