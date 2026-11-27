import unittest
import json
import sys
from browser_automation.bundle import (
    CrawlBundle,
    CrawlRecord,
    CrawlManifest,
    PageType,
    AccessState,
    ObservationMetadata,
    TriState,
)


class CrawlBundleContractTests(unittest.TestCase):

    def test_playwright_independence(self):
        """Verify CrawlBundle can be imported and used without importing Playwright."""
        bundle = CrawlBundle(base_url="https://example.com")
        self.assertNotIn("playwright", sys.modules.get("browser_automation.bundle", "").__dict__)

        record = CrawlRecord(
            canonical_url="https://example.com/p1",
            source_url="https://example.com/p1",
            page_type=PageType.PRODUCT,
            http_status=200,
            content_type="text/html",
            access_state=AccessState.ACCESSIBLE,
            fetch_timestamp="2026-11-20T12:00:00Z",
            rendered_html="<html><body>Product 1</body></html>",
            visible_text="Product 1",
            script_urls=["https://example.com/app.js"],
        )
        self.assertEqual(record.page_type, PageType.PRODUCT)
        self.assertEqual(record.access_state, AccessState.ACCESSIBLE)

    def test_serialization_and_deserialization(self):
        """Verify deterministic serialization to JSON and back."""
        manifest = CrawlManifest(
            base_url="https://example.com",
            total_discovered=3,
            discovered_urls=["https://example.com", "https://example.com/about", "https://example.com/contact"],
            selected_urls=["https://example.com", "https://example.com/about"],
            skipped_urls=[{"url": "https://example.com/contact", "reason": "Quota"}],
            failed_urls=[],
            crawl_start_time="2026-11-20T12:00:00Z",
            crawl_end_time="2026-11-20T12:01:00Z",
        )
        obs = ObservationMetadata(
            newsletter_form=TriState.OBSERVED,
            email_input=TriState.OBSERVED,
            phone_input=TriState.NOT_OBSERVED,
            observed_form_actions=["/newsletter/subscribe"],
            observed_input_labels=["Email address"],
        )
        record = CrawlRecord(
            canonical_url="https://example.com",
            source_url="https://example.com",
            page_type=PageType.HOMEPAGE,
            http_status=200,
            content_type="text/html; charset=utf-8",
            access_state=AccessState.ACCESSIBLE,
            fetch_timestamp="2026-11-20T12:00:05Z",
            rendered_html="<html><body>Welcome</body></html>",
            visible_text="Welcome",
            script_urls=["https://example.com/analytics.js"],
            observation_metadata=obs,
            provisional_redirect_chain=["https://example.com"],
            provisional_response_headers={"content-type": "text/html"},
        )
        bundle = CrawlBundle(
            base_url="https://example.com",
            records=[record],
            manifest=manifest,
            crawler_user_agent="DLitheBot/1.0",
        )

        json_str = bundle.to_json()
        reconstructed = CrawlBundle.from_json(json_str)

        self.assertEqual(reconstructed.base_url, bundle.base_url)
        self.assertEqual(reconstructed.crawler_user_agent, bundle.crawler_user_agent)
        self.assertEqual(len(reconstructed.records), 1)

        r = reconstructed.records[0]
        self.assertEqual(r.canonical_url, record.canonical_url)
        self.assertEqual(r.page_type, PageType.HOMEPAGE)
        self.assertEqual(r.access_state, AccessState.ACCESSIBLE)
        self.assertEqual(r.observation_metadata.newsletter_form, TriState.OBSERVED)
        self.assertTrue(r.observation_metadata.has_newsletter_form)
        self.assertTrue(r.observation_metadata.has_email_input)
        self.assertEqual(r.observation_metadata.observed_form_actions, ["/newsletter/subscribe"])
        self.assertEqual(reconstructed.manifest.total_discovered, 3)

    def test_missing_required_fields_and_malformed_json(self):
        """Regression test: verify deserialization rejects missing required fields and malformed json."""
        # Malformed JSON
        with self.assertRaises(ValueError):
            CrawlBundle.from_json("{broken json")

        # Missing base_url
        with self.assertRaises(ValueError):
            CrawlBundle.from_dict({"records": []})

        # Missing required record fields
        incomplete_record_dict = {
            "base_url": "https://example.com",
            "records": [
                {
                    "canonical_url": "https://example.com",
                    # missing source_url, page_type, access_state, fetch_timestamp
                }
            ]
        }
        with self.assertRaises(ValueError):
            CrawlBundle.from_dict(incomplete_record_dict)

        # Invalid enum values
        invalid_enum_dict = {
            "base_url": "https://example.com",
            "records": [
                {
                    "canonical_url": "https://example.com",
                    "source_url": "https://example.com",
                    "page_type": "invalid_page_type",
                    "access_state": "Accessible",
                    "fetch_timestamp": "2026-11-20T12:00:00Z",
                }
            ]
        }
        with self.assertRaises(ValueError):
            CrawlBundle.from_dict(invalid_enum_dict)


if __name__ == "__main__":
    unittest.main()
