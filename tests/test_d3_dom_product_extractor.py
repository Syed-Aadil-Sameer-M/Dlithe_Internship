"""Unit tests for D3 Day 3 DOM Product Card Fallback Extractor & Price Normalizer.

All tests run completely offline without network requests and verify:
- multiple product cards
- title extraction
- relative product URLs
- ₹ / INR prices
- USD prices
- EUR prices
- GBP prices
- thousands separators
- decimal prices
- missing price
- missing title
- missing URL
- ambiguous currency
- noisy/irrelevant price text
- malformed/minimal HTML
- accessible CrawlRecord is processed
- blocked/inaccessible CrawlRecord is not processed
- page_type is available for routing where appropriate
- EvidenceRecord contract adherence (EvidenceMethod.DOM, confidence, status)
"""

from datetime import datetime, timezone
import pytest

from scraper_detection.extraction.dom_product_extractor import (
    CrawlRecordInput,
    DOMProductExtractor,
    extract_products_dom,
    normalize_price_and_currency,
    normalize_whitespace,
)
from scraper_detection.schemas.evidence import (
    EvidenceMethod,
    EvidenceStatus,
)


def test_multiple_product_cards():
    html = """
    <html>
    <body>
        <div class="product-grid">
            <div class="product-card">
                <a class="product-title" href="/products/tee-1">Cotton T-Shirt</a>
                <span class="price">$19.99</span>
            </div>
            <div class="product-card">
                <a class="product-title" href="/products/tee-2">Linen T-Shirt</a>
                <span class="price">$24.99</span>
            </div>
            <div class="product-card">
                <a class="product-title" href="/products/hoodie">Classic Hoodie</a>
                <span class="price">$49.99</span>
            </div>
        </div>
    </body>
    </html>
    """
    products = extract_products_dom(html, source_url="https://example.com/collections/all")
    assert len(products) == 3

    assert products[0].get("product.title") == "Cotton T-Shirt"
    assert products[0].get("product.price") == 19.99
    assert products[0].get("product.currency") == "USD"
    assert products[0].get("product.url") == "https://example.com/products/tee-1"

    assert products[1].get("product.title") == "Linen T-Shirt"
    assert products[1].get("product.price") == 24.99

    assert products[2].get("product.title") == "Classic Hoodie"
    assert products[2].get("product.price") == 49.99


def test_title_extraction_with_whitespace():
    html = """
    <div class="product-item">
        <h3 class="product__title">
            \n\t  Breathable    Running   Shoe  \n
        </h3>
        <a href="/products/shoe" class="product-link">View</a>
        <div class="price">$89.00</div>
    </div>
    """
    products = extract_products_dom(html, source_url="https://example.com")
    assert len(products) == 1
    p = products[0]

    title_rec = p.get_record("product.title")
    assert title_rec is not None
    assert title_rec.status == EvidenceStatus.FOUND
    assert title_rec.value == "Breathable Running Shoe"
    assert title_rec.method == EvidenceMethod.DOM
    assert title_rec.confidence == 0.8


def test_relative_product_urls():
    html = """
    <div class="product-card">
        <a href="items/denim-jacket">Denim Jacket</a>
        <span class="price">$65.00</span>
    </div>
    """
    products = extract_products_dom(html, source_url="https://store.example.com/shop/apparel/")
    assert len(products) == 1
    p = products[0]

    url_rec = p.get_record("product.url")
    assert url_rec is not None
    assert url_rec.status == EvidenceStatus.FOUND
    assert url_rec.value == "https://store.example.com/shop/apparel/items/denim-jacket"
    assert url_rec.method == EvidenceMethod.DOM


def test_inr_prices():
    test_cases = [
        ("₹999", 999.0, "INR"),
        ("₹ 999", 999.0, "INR"),
        ("INR 999", 999.0, "INR"),
        ("INR 1,299", 1299.0, "INR"),
        ("INR 1,00,000", 100000.0, "INR"),
        ("Rs. 1,499.00", 1499.0, "INR"),
    ]

    for price_str, expected_price, expected_currency in test_cases:
        html = f"""
        <div class="product-card">
            <h2>Ethnic Kurta</h2>
            <a href="/p/1">Details</a>
            <span class="price">{price_str}</span>
        </div>
        """
        products = extract_products_dom(html, source_url="https://example.in")
        assert len(products) == 1, f"Failed extracting card for {price_str}"
        p = products[0]
        assert p.get("product.price") == expected_price, f"Wrong price for {price_str}"
        assert p.get("product.currency") == expected_currency, f"Wrong currency for {price_str}"


def test_usd_prices():
    test_cases = [
        ("$29.99", 29.99, "USD"),
        ("USD 29.99", 29.99, "USD"),
        ("$ 1,299.00", 1299.0, "USD"),
    ]

    for price_str, expected_price, expected_curr in test_cases:
        html = f"""
        <div class="product-box">
            <span class="product-title">Everyday Backpack</span>
            <a href="/backpack">Link</a>
            <span class="price-amount">{price_str}</span>
        </div>
        """
        products = extract_products_dom(html, source_url="https://example.com")
        assert len(products) == 1
        p = products[0]
        assert p.get("product.price") == expected_price
        assert p.get("product.currency") == expected_curr


def test_eur_prices():
    test_cases = [
        ("€49.90", 49.90, "EUR"),
        ("49,90 €", 49.90, "EUR"),
        ("€ 1.299,50", 1299.50, "EUR"),
        ("EUR 49.90", 49.90, "EUR"),
    ]

    for price_str, expected_price, expected_curr in test_cases:
        html = f"""
        <div class="product-card">
            <h3>Leather Boots</h3>
            <a href="/boots">View</a>
            <span class="price">{price_str}</span>
        </div>
        """
        products = extract_products_dom(html, source_url="https://example.eu")
        assert len(products) == 1
        p = products[0]
        assert p.get("product.price") == expected_price
        assert p.get("product.currency") == expected_curr


def test_gbp_prices():
    test_cases = [
        ("£39.99", 39.99, "GBP"),
        ("GBP 39.99", 39.99, "GBP"),
        ("£ 1,450.00", 1450.0, "GBP"),
    ]

    for price_str, expected_price, expected_curr in test_cases:
        html = f"""
        <div class="product-tile">
            <h4>Wool Sweater</h4>
            <a href="/sweater">Link</a>
            <span class="price">{price_str}</span>
        </div>
        """
        products = extract_products_dom(html, source_url="https://example.co.uk")
        assert len(products) == 1
        p = products[0]
        assert p.get("product.price") == expected_price
        assert p.get("product.currency") == expected_curr


def test_thousands_and_decimals():
    # Standard thousand comma, Indian comma, European thousand dot and decimal comma
    p1, c1, _ = normalize_price_and_currency("$1,299.99")
    assert p1 == 1299.99
    assert c1 == "USD"

    p2, c2, _ = normalize_price_and_currency("INR 1,00,000")
    assert p2 == 100000.0
    assert c2 == "INR"

    p3, c3, _ = normalize_price_and_currency("€ 1.299,50")
    assert p3 == 1299.50
    assert c3 == "EUR"


def test_missing_price():
    html = """
    <div class="product-card">
        <a class="product-title" href="/products/limited-drop">Limited Drop Jacket</a>
        <div class="availability">Out of stock - Price unavailable</div>
    </div>
    """
    products = extract_products_dom(html, source_url="https://example.com")
    assert len(products) == 1
    p = products[0]

    assert p.get("product.title") == "Limited Drop Jacket"
    assert p.get("product.url") == "https://example.com/products/limited-drop"

    price_rec = p.get_record("product.price")
    assert price_rec is not None
    assert price_rec.status == EvidenceStatus.NOT_OBSERVED
    assert price_rec.value is None

    curr_rec = p.get_record("product.currency")
    assert curr_rec is not None
    assert curr_rec.status == EvidenceStatus.NOT_OBSERVED
    assert curr_rec.value is None


def test_missing_title():
    html = """
    <div class="product-card">
        <a href="/products/mystery-item"><img src="item.jpg" /></a>
        <span class="price">$15.00</span>
    </div>
    """
    products = extract_products_dom(html, source_url="https://example.com")
    assert len(products) == 1
    p = products[0]

    title_rec = p.get_record("product.title")
    assert title_rec is not None
    assert title_rec.status == EvidenceStatus.NOT_OBSERVED
    assert title_rec.value is None

    assert p.get("product.price") == 15.0
    assert p.get("product.url") == "https://example.com/products/mystery-item"


def test_missing_url():
    html = """
    <div class="product-card">
        <span class="product-title">In-Store Only Mug</span>
        <span class="price">$12.50</span>
    </div>
    """
    products = extract_products_dom(html, source_url="https://example.com")
    assert len(products) == 1
    p = products[0]

    assert p.get("product.title") == "In-Store Only Mug"
    assert p.get("product.price") == 12.50

    url_rec = p.get_record("product.url")
    assert url_rec is not None
    assert url_rec.status == EvidenceStatus.NOT_OBSERVED
    assert url_rec.value is None


def test_ambiguous_currency_preserves_notation():
    # Ambiguous currency notation 'kr' should be preserved and marked UNVERIFIED, not guessed as SEK/NOK/DKK
    html = """
    <div class="product-card">
        <a href="/nordic-chair">Nordic Minimalist Chair</a>
        <span class="price">kr 450</span>
    </div>
    """
    products = extract_products_dom(html, source_url="https://example.org")
    assert len(products) == 1
    p = products[0]

    assert p.get("product.price") == 450.0

    curr_rec = p.get_record("product.currency")
    assert curr_rec is not None
    assert curr_rec.status == EvidenceStatus.UNVERIFIED
    assert curr_rec.value == "kr"


def test_ambiguous_currency_resolved_by_page_meta():
    # When page explicitly provides currency metadata (e.g. meta priceCurrency), it disambiguates
    html = """
    <html>
    <head>
        <meta itemprop="priceCurrency" content="SEK">
    </head>
    <body>
        <div class="product-card">
            <a href="/nordic-table">Nordic Table</a>
            <span class="price">kr 890</span>
        </div>
    </body>
    </html>
    """
    products = extract_products_dom(html, source_url="https://example.se")
    assert len(products) == 1
    p = products[0]

    assert p.get("product.price") == 890.0
    curr_rec = p.get_record("product.currency")
    assert curr_rec.status == EvidenceStatus.FOUND
    assert curr_rec.value == "SEK"


def test_noisy_irrelevant_price_text():
    # Handles noisy text such as 'Save 20%', 'Only 3 left', and model numbers
    html = """
    <div class="product-card">
        <h3>Smart Fitness Tracker</h3>
        <a href="/fitness-tracker">View</a>
        <div class="price-container">
            <span class="was-price">Was $59.99</span>
            <span class="current-price">$29.99</span>
            <span class="discount-badge">Save 50% Today!</span>
            <span class="inventory">Only 2 items left in stock (SKU: 99482)</span>
        </div>
    </div>
    """
    products = extract_products_dom(html, source_url="https://example.com")
    assert len(products) == 1
    p = products[0]

    assert p.get("product.title") == "Smart Fitness Tracker"
    assert p.get("product.price") == 29.99
    assert p.get("product.currency") == "USD"
    assert p.get("product.original_price") == 59.99
    assert p.get("product.discount_price") == 29.99


def test_malformed_minimal_html():
    # Malformed HTML, unclosed tags, empty elements
    html = """
    <div class="product-card">
        <a href="/item/1">Item Alpha
        <span class="price">$10.00
    </div>
    <div class="not-a-product">
        <span>No link or title</span>
    </div>
    """
    products = extract_products_dom(html, source_url="https://example.com")
    assert len(products) == 1
    assert products[0].get("product.title") == "Item Alpha"
    assert products[0].get("product.price") == 10.0


def test_crawl_record_accessible_processed():
    record = CrawlRecordInput(
        source_url="https://example.com/collection",
        canonical_url="https://example.com/collection",
        page_type="collection",
        rendered_html="""
        <div class="product-card">
            <a href="/products/jacket">Winter Jacket</a>
            <span class="price">$120.00</span>
        </div>
        """,
        access_state="Accessible",
        fetch_timestamp="2026-11-21T18:00:00Z",
    )
    extractor = DOMProductExtractor(confidence=0.85)
    products = extractor.extract_from_crawl_record(record)
    assert len(products) == 1

    p = products[0]
    assert p.get("product.title") == "Winter Jacket"
    assert p.get("product.price") == 120.0
    assert p.get_record("product.title").confidence == 0.85
    assert p.get_record("product.title").source_url == "https://example.com/collection"


def test_crawl_record_blocked_inaccessible_skipped():
    blocked_states = ["Blocked", "Unavailable", "Error"]

    for state in blocked_states:
        record = CrawlRecordInput(
            source_url="https://example.com/products",
            rendered_html="""
            <div class="product-card">
                <a href="/p1">Secret Product</a>
                <span class="price">$99.00</span>
            </div>
            """,
            access_state=state,
        )
        extractor = DOMProductExtractor()
        products = extractor.extract_from_crawl_record(record)
        assert products == [], f"Should return empty list for access_state={state}"


def test_crawl_record_page_type_routing():
    extractor = DOMProductExtractor()

    # When restricted to collection or product, about pages are skipped
    about_record = CrawlRecordInput(
        source_url="https://example.com/about",
        page_type="about",
        rendered_html="""
        <div class="product-card">
            <a href="/p1">Featured</a>
            <span class="price">$10.00</span>
        </div>
        """,
        access_state="Accessible",
    )
    products_about = extractor.extract_from_crawl_record(
        about_record,
        allowed_page_types={"collection", "product"},
    )
    assert products_about == []

    # Collection page is allowed
    collection_record = CrawlRecordInput(
        source_url="https://example.com/collection",
        page_type="collection",
        rendered_html="""
        <div class="product-card">
            <a href="/p1">Collection Item</a>
            <span class="price">$10.00</span>
        </div>
        """,
        access_state="Accessible",
    )
    products_col = extractor.extract_from_crawl_record(
        collection_record,
        allowed_page_types={"collection", "product"},
    )
    assert len(products_col) == 1
    assert products_col[0].get("product.title") == "Collection Item"


def test_evidence_contract_dom_method():
    html = """
    <div class="product-card">
        <a href="/product/test">Test Title</a>
        <span class="price">$25.00</span>
    </div>
    """
    fixed_time = datetime(2026, 11, 21, 12, 0, 0, tzinfo=timezone.utc)
    products = extract_products_dom(
        html,
        source_url="https://example.com/test",
        observed_at=fixed_time,
        confidence=0.8,
    )
    assert len(products) == 1
    p = products[0]

    for field_name in p.records:
        rec = p.get_record(field_name)
        assert rec.method == EvidenceMethod.DOM
        assert rec.confidence == 0.8
        assert rec.source_url == "https://example.com/test"
        assert rec.observed_at == fixed_time
