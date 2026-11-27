import unittest
from browser_automation.discovery import discover_and_select_pages, classify_page_type
from browser_automation.bundle import PageType


class PageDiscoveryTests(unittest.TestCase):

    def test_classify_page_type(self):
        base = "https://example.com"
        self.assertEqual(classify_page_type("https://example.com", base), PageType.HOMEPAGE)
        self.assertEqual(classify_page_type("https://example.com/", base), PageType.HOMEPAGE)
        self.assertEqual(classify_page_type("https://example.com/collections/summer", base), PageType.COLLECTION)
        self.assertEqual(classify_page_type("https://example.com/category/shoes", base), PageType.COLLECTION)
        self.assertEqual(classify_page_type("https://example.com/products/leather-bag", base), PageType.PRODUCT)
        self.assertEqual(classify_page_type("https://example.com/about-us", base), PageType.ABOUT)
        self.assertEqual(classify_page_type("https://example.com/pages/contact", base), PageType.CONTACT)
        self.assertEqual(classify_page_type("https://example.com/terms-and-conditions", base), PageType.OTHER)

    def test_deterministic_page_selection_and_quotas(self):
        base = "https://example.com"
        links = [
            "/collections/shoes",
            "/collections/shirts",
            "/collections/hats",  # alphabetical order: hats, shirts, shoes -> selects hats & shirts, skips shoes
            "/products/item-b",
            "/products/item-a",
            "/products/item-c",  # alphabetical order: item-a, item-b, item-c -> selects item-a & item-b, skips item-c
            "/about",
            "/pages/about-us",  # 2nd about, should be skipped
            "/contact",
            "/terms",
            "https://cross-site.com/foo",  # cross origin, skipped
            "/collections/shoes?utm_source=ad",  # duplicate of /collections/shoes
        ]

        selected, discovered, skipped = discover_and_select_pages(
            base_url=base,
            extracted_links=links,
            max_pages=7,
        )

        selected_dict = {}
        for url, ptype in selected:
            selected_dict.setdefault(ptype, []).append(url)

        # Homepage is always selected
        self.assertEqual(len(selected_dict.get(PageType.HOMEPAGE, [])), 1)

        # Collections max 2
        collections = selected_dict.get(PageType.COLLECTION, [])
        self.assertEqual(len(collections), 2)
        # Deterministic sorting (alphabetical: hats, shirts)
        self.assertEqual(collections, ["https://example.com/collections/hats", "https://example.com/collections/shirts"])

        # Products max 2
        products = selected_dict.get(PageType.PRODUCT, [])
        self.assertEqual(len(products), 2)
        self.assertEqual(products, ["https://example.com/products/item-a", "https://example.com/products/item-b"])

        # About max 1
        abouts = selected_dict.get(PageType.ABOUT, [])
        self.assertEqual(len(abouts), 1)

        # Contact max 1
        contacts = selected_dict.get(PageType.CONTACT, [])
        self.assertEqual(len(contacts), 1)

        # Cross origin properly skipped
        skipped_reasons = [s["reason"] for s in skipped]
        self.assertTrue(any("same-site" in r for r in skipped_reasons))
        self.assertTrue(any("collection quota" in r for r in skipped_reasons))
        self.assertTrue(any("product quota" in r for r in skipped_reasons))


if __name__ == "__main__":
    unittest.main()
