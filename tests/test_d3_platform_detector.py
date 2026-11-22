"""Focused unit tests for D3 Day 5 Platform Fingerprint Detector.

Verifies deterministic platform detection for:
- Shopify positive detection
- WooCommerce positive detection
- Magento positive detection
- no-platform / ordinary HTML
- ambiguous or weak evidence -> Unverified
- conflicting platform signals -> Unverified
- matching indicators preservation
- confidence within [0.0, 1.0]
- D2 CrawlRecord compatibility (Accessible vs Blocked)
"""

from datetime import datetime, timezone
import pytest

from scraper_detection.detection.platform_detector import (
    PLATFORM_MAGENTO,
    PLATFORM_SHOPIFY,
    PLATFORM_WOOCOMMERCE,
    PlatformDetector,
    detect_ecommerce_platform,
)
from scraper_detection.extraction.dom_product_extractor import CrawlRecordInput
from scraper_detection.schemas.evidence import (
    EvidenceMethod,
    EvidenceStatus,
)


def test_shopify_positive_detection():
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta name="shopify-digital-wallet" content="/12345/digital_wallets/dialog">
        <script src="https://cdn.shopify.com/s/files/1/0000/files/theme.js"></script>
        <script>
            window.Shopify = window.Shopify || {};
            Shopify.theme = {"name": "Dawn", "id": 123456};
        </script>
    </head>
    <body>
        <div id="shopify-section-header" class="shopify-section">Header Content</div>
    </body>
    </html>
    """
    res = detect_ecommerce_platform(html, source_url="https://acme-fashion.com")
    ev = res.evidence

    assert ev.field == "technology.ecommerce_platform"
    assert ev.value == PLATFORM_SHOPIFY
    assert ev.status == EvidenceStatus.FOUND
    assert ev.source_url == "https://acme-fashion.com"
    assert 0.85 <= ev.confidence <= 1.0

    # Indicators preserved
    assert len(res.matched_indicators) >= 3
    indicator_names = [ind.indicator_name for ind in res.matched_indicators]
    assert "shopify_cdn_script" in indicator_names or "shopify_cdn_asset" in indicator_names
    assert "shopify_meta_wallet" in indicator_names
    assert "shopify_window_object" in indicator_names


def test_woocommerce_positive_detection():
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta name="generator" content="WooCommerce 8.6.0" />
        <script src="https://example.com/wp-content/plugins/woocommerce/assets/js/frontend/woocommerce.min.js"></script>
        <script>
            /* <![CDATA[ */
            var wc_add_to_cart_params = {"ajax_url": "/wp-admin/admin-ajax.php"};
            /* ]]> */
        </script>
    </head>
    <body class="archive post-type-archive post-type-archive-product woocommerce woocommerce-page">
        <div class="product">
            <span class="woocommerce-Price-amount amount">$25.00</span>
        </div>
    </body>
    </html>
    """
    res = detect_ecommerce_platform(html, source_url="https://artisan-goods.com/shop")
    ev = res.evidence

    assert ev.field == "technology.ecommerce_platform"
    assert ev.value == PLATFORM_WOOCOMMERCE
    assert ev.status == EvidenceStatus.FOUND
    assert ev.source_url == "https://artisan-goods.com/shop"
    assert 0.85 <= ev.confidence <= 1.0

    indicator_names = [ind.indicator_name for ind in res.matched_indicators]
    assert "woocommerce_generator_meta" in indicator_names
    assert "woocommerce_body_class" in indicator_names
    assert "woocommerce_price_amount_class" in indicator_names


def test_magento_positive_detection():
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <script src="https://store.example.com/static/version1600000000/frontend/Magento/luma/en_US/mage/cookies.js"></script>
        <script type="text/x-magento-init">
        {
            "*": {
                "mage/cookies": {
                    "expires": null,
                    "path": "/",
                    "domain": ".example.com",
                    "secure": false,
                    "lifetime": "3600"
                }
            }
        }
        </script>
    </head>
    <body class="catalog-product-view page-layout-1column">
        <form data-mage-init='{"catalogAddToCart":{}}' action="/checkout/cart/add">
            <input name="form_key" type="hidden" value="xyz123" />
            <button type="submit">Add to Cart</button>
        </form>
    </body>
    </html>
    """
    res = detect_ecommerce_platform(html, source_url="https://store.example.com/item-1")
    ev = res.evidence

    assert ev.field == "technology.ecommerce_platform"
    assert ev.value == PLATFORM_MAGENTO
    assert ev.status == EvidenceStatus.FOUND
    assert ev.source_url == "https://store.example.com/item-1"
    assert 0.85 <= ev.confidence <= 1.0

    indicator_names = [ind.indicator_name for ind in res.matched_indicators]
    assert "magento_data_mage_init" in indicator_names
    assert "magento_text_x_init_script" in indicator_names
    assert "magento_mage_js_script" in indicator_names or "magento_static_frontend_script" in indicator_names


def test_no_platform_ordinary_html():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Tech Blog & Articles</title>
        <meta name="description" content="Personal software engineering blog." />
    </head>
    <body>
        <h1>Welcome to My Blog</h1>
        <p>No e-commerce engines or scripts here.</p>
    </body>
    </html>
    """
    res = detect_ecommerce_platform(html, source_url="https://myblog.dev")
    ev = res.evidence

    assert ev.field == "technology.ecommerce_platform"
    assert ev.value is None
    assert ev.status == EvidenceStatus.NOT_OBSERVED
    assert ev.confidence == 1.0
    assert res.matched_indicators == []


def test_weak_evidence_results_in_unverified():
    # Only a single weak form action marker "/cart/add", with no other Shopify signals
    html = """
    <html>
    <body>
        <form action="/cart/add" method="post">
            <button type="submit">Add</button>
        </form>
    </body>
    </html>
    """
    res = detect_ecommerce_platform(html, source_url="https://generic-cart.com")
    ev = res.evidence

    assert ev.field == "technology.ecommerce_platform"
    assert ev.value == PLATFORM_SHOPIFY
    # Must be UNVERIFIED due to insufficient/weak evidence
    assert ev.status == EvidenceStatus.UNVERIFIED
    assert ev.confidence < 0.70
    assert 0.0 <= ev.confidence <= 1.0


def test_conflicting_evidence_results_in_unverified():
    # Conflicting strong signals from both Shopify and Magento on the same page
    html = """
    <html>
    <head>
        <script src="https://cdn.shopify.com/shopifycloud/shopify.js"></script>
    </head>
    <body>
        <div data-mage-init='{"someComponent":{}}'>Content</div>
    </body>
    </html>
    """
    res = detect_ecommerce_platform(html, source_url="https://hybrid-test.com")
    ev = res.evidence

    assert ev.status == EvidenceStatus.UNVERIFIED
    assert ev.confidence == 0.50
    assert res.confidence_breakdown["conflict"] is True


def test_crawl_record_compatibility_accessible_vs_blocked():
    detector = PlatformDetector()

    # 1. Accessible CrawlRecord
    accessible_rec = CrawlRecordInput(
        source_url="https://example-shop.com",
        rendered_html="""
        <html>
        <head><script src="https://cdn.shopify.com/s/files/script.js"></script></head>
        <body class="shopify-section">Content</body>
        </html>
        """,
        access_state="Accessible",
    )
    res_acc = detector.detect_from_crawl_record(accessible_rec)
    assert res_acc.evidence.status == EvidenceStatus.FOUND
    assert res_acc.evidence.value == PLATFORM_SHOPIFY

    # 2. Blocked CrawlRecord
    blocked_rec = CrawlRecordInput(
        source_url="https://example-shop.com/blocked",
        rendered_html="<html><body>Cloudflare Blocked</body></html>",
        access_state="Blocked",
    )
    res_block = detector.detect_from_crawl_record(blocked_rec)
    assert res_block.evidence.status == EvidenceStatus.BLOCKED
    assert res_block.evidence.value is None


def test_indicators_preservation_and_confidence_range():
    html = """
    <html>
    <head>
        <meta name="generator" content="WooCommerce 8.0" />
    </head>
    <body class="woocommerce">
        <span class="woocommerce-Price-amount">$100</span>
    </body>
    </html>
    """
    res = detect_ecommerce_platform(html, source_url="https://woo-test.com")

    for ind in res.matched_indicators:
        assert ind.platform == PLATFORM_WOOCOMMERCE
        assert ind.signal_type in ("meta_tag", "html_class", "script_url", "asset_url", "inline_script", "html_attribute", "form_action", "form_attribute")
        assert ind.strength in ("strong", "medium", "weak")
        assert ind.indicator_name != ""
        assert ind.matched_value != ""
        assert isinstance(ind.method, EvidenceMethod)

    assert 0.0 <= res.evidence.confidence <= 1.0
