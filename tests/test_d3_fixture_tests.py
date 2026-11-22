"""Fixture-first test suite for D3 Extraction & Detection modules (Day 6).

Executes completely offline using local HTML fixtures in tests/fixtures/.
Covers:
1. JSON-LD product extraction (valid Product, multiple blocks, @graph, malformed, missing fields)
2. Missing price (title extracted, price NOT_FOUND and not fabricated)
3. Sale price (sale vs original price distinguished in JSON-LD and DOM)
4. Duplicate product (duplicate representations deduplicated)
5. Malformed HTML (graceful recovery without exceptions)
6. Contact and social links (email, phone, Instagram, Facebook, YouTube, X, LinkedIn with source URLs)
7. Negative cases (ordinary HTML with no products, contacts, social links, or ecommerce platforms)
8. D2 CrawlRecord integration with fixtures
"""

from pathlib import Path
import pytest

from scraper_detection.detection.platform_detector import (
    detect_ecommerce_platform,
)
from scraper_detection.extraction.contact_social_extractor import (
    extract_contact_and_social,
)
from scraper_detection.extraction.dom_product_extractor import (
    CrawlRecordInput,
    extract_products_dom,
)
from scraper_detection.extraction.product_extractor import (
    extract_products_json_ld,
)
from scraper_detection.extraction.store_extractor import (
    extract_store_details,
)
from scraper_detection.schemas.evidence import (
    EvidenceMethod,
    EvidenceStatus,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(filename: str) -> str:
    """Load a UTF-8 encoded test fixture from tests/fixtures/."""
    fixture_path = FIXTURES_DIR / filename
    if not fixture_path.exists():
        raise FileNotFoundError(f"Fixture not found: {fixture_path}")
    return fixture_path.read_text(encoding="utf-8")


def test_fixture_valid_json_ld_product():
    """1. Valid Product JSON-LD produces complete EvidenceRecords with JSON_LD method."""
    html = load_fixture("product_valid_json_ld.html")
    source_url = "https://teacraft.example.com/products/artisan-ceramic-teapot"

    products = extract_products_json_ld(html, source_url=source_url)
    assert len(products) == 1
    p = products[0]

    # Title
    title_rec = p.get_record("product.title")
    assert title_rec is not None
    assert title_rec.status == EvidenceStatus.FOUND
    assert title_rec.value == "Artisan Ceramic Teapot"
    assert title_rec.method == EvidenceMethod.JSON_LD
    assert title_rec.source_url == source_url
    assert title_rec.confidence == 1.0

    # Price & Currency
    price_rec = p.get_record("product.price")
    assert price_rec.status == EvidenceStatus.FOUND
    assert price_rec.value == 48.50

    curr_rec = p.get_record("product.currency")
    assert curr_rec.status == EvidenceStatus.FOUND
    assert curr_rec.value == "USD"

    # Description & Availability
    desc_rec = p.get_record("product.description")
    assert desc_rec.status == EvidenceStatus.FOUND
    assert "Handmade ceramic teapot" in desc_rec.value

    avail_rec = p.get_record("product.availability")
    assert avail_rec.status == EvidenceStatus.FOUND
    assert "InStock" in avail_rec.value

    # URL
    url_rec = p.get_record("product.url")
    assert url_rec.status == EvidenceStatus.FOUND
    assert url_rec.value == source_url


def test_fixture_multiple_blocks_and_graph():
    """1. Multiple JSON-LD script blocks and @graph hierarchies unpack safely."""
    html = load_fixture("product_multiple_blocks_graph.html")
    source_url = "https://studioterra.example.com"

    products = extract_products_json_ld(html, source_url=source_url)

    # Broken script block is ignored safely; the 2 valid products are extracted
    assert len(products) == 2
    titles = [p.get("product.title") for p in products]
    assert "Glazed Terracotta Planter" in titles
    assert "Copper Watering Can" in titles

    prices = [p.get("product.price") for p in products]
    assert 34.00 in prices
    assert 62.00 in prices


def test_fixture_missing_price_json_ld_and_dom():
    """2. When title exists but price is absent, price is NOT_FOUND and never fabricated."""
    html = load_fixture("product_missing_price.html")
    source_url = "https://woodcraft.example.com/furniture/walnut-table"

    # In JSON-LD
    products_json = extract_products_json_ld(html, source_url=source_url)
    assert len(products_json) == 1
    p_json = products_json[0]

    assert p_json.get("product.title") == "Handmade Walnut Dining Table"
    price_rec_json = p_json.get_record("product.price")
    assert price_rec_json.status == EvidenceStatus.NOT_FOUND
    assert price_rec_json.value is None

    curr_rec_json = p_json.get_record("product.currency")
    assert curr_rec_json.status == EvidenceStatus.NOT_FOUND
    assert curr_rec_json.value is None

    # In DOM fallback
    products_dom = extract_products_dom(html, source_url=source_url)
    assert len(products_dom) == 1
    p_dom = products_dom[0]

    assert p_dom.get("product.title") == "Handmade Walnut Dining Table"
    price_rec_dom = p_dom.get_record("product.price")
    assert price_rec_dom.status == EvidenceStatus.NOT_FOUND
    assert price_rec_dom.value is None


def test_fixture_sale_price_distinction():
    """3. Current/sale price and original/compare-at price are correctly distinguished."""
    html = load_fixture("product_sale_price.html")
    source_url = "https://northwind.example.com/products/merino-cardigan"

    # In JSON-LD
    products_json = extract_products_json_ld(html, source_url=source_url)
    assert len(products_json) == 1
    pj = products_json[0]
    assert pj.get("product.price") == 89.00
    assert pj.get("product.original_price") == 140.00
    assert pj.get("product.currency") == "USD"

    # In DOM
    products_dom = extract_products_dom(html, source_url=source_url)
    assert len(products_dom) == 1
    pd = products_dom[0]
    assert pd.get("product.title") == "Merino Wool Cardigan"
    assert pd.get("product.price") == 89.00
    assert pd.get("product.original_price") == 140.00
    assert pd.get("product.discount_price") == 89.00
    assert pd.get("product.currency") == "USD"


def test_fixture_duplicate_product_handling():
    """4. Duplicate product instances in HTML are deduplicated deterministically."""
    html = load_fixture("product_duplicate.html")
    source_url = "https://urbansoles.example.com"

    # In JSON-LD: 2 identical blocks -> 1 distinct product
    products_json = extract_products_json_ld(html, source_url=source_url)
    assert len(products_json) == 1
    assert products_json[0].get("product.title") == "Urban Canvas Low-Tops"

    # In DOM: 2 identical product cards -> 1 distinct product
    products_dom = extract_products_dom(html, source_url=source_url)
    assert len(products_dom) == 1
    assert products_dom[0].get("product.title") == "Urban Canvas Low-Tops"
    assert products_dom[0].get("product.price") == 55.00


def test_fixture_malformed_html_robustness():
    """5. Deliberately malformed HTML handles gracefully without crashes or exceptions."""
    html = load_fixture("malformed_html.html")
    source_url = "https://example.com/messy"

    # JSON-LD handles syntax errors safely
    products_json = extract_products_json_ld(html, source_url=source_url)
    assert products_json == []

    # DOM extractor extracts the resilient card
    products_dom = extract_products_dom(html, source_url=source_url)
    assert len(products_dom) == 1
    p = products_dom[0]
    assert p.get("product.title") == "Resilient Phone Case"
    assert p.get("product.price") == 19.99


def test_fixture_store_contact_and_social():
    """6. Extract store details, public email, phone, and official social links with source URLs."""
    html = load_fixture("store_contact_social.html")
    source_url = "https://komorebi.store/contact-and-about"

    # Store Details
    store_details = extract_store_details(html, source_url=source_url, page_type="about")
    assert store_details.get("store.name") == "Komorebi Botanicals"
    assert store_details.get_record("store.name").status == EvidenceStatus.FOUND
    assert store_details.get_record("store.name").source_url == source_url
    assert "Founded in Kyoto in 2017" in store_details.get("store.about_text")

    # Contact & Social
    contact_social = extract_contact_and_social(html, source_url=source_url)

    # Email & Phone
    email_rec = contact_social.get_record("contact.email")
    assert email_rec.status == EvidenceStatus.FOUND
    assert email_rec.value == "care@komorebi.store"
    assert email_rec.source_url == source_url

    phone_rec = contact_social.get_record("contact.phone")
    assert phone_rec.status == EvidenceStatus.FOUND
    assert phone_rec.value == "+18005550244"
    assert phone_rec.source_url == source_url

    # Social Profiles
    ig_rec = contact_social.get_record("social.instagram")
    assert ig_rec.status == EvidenceStatus.FOUND
    assert ig_rec.value == "https://www.instagram.com/komorebi_botanicals/"
    assert ig_rec.source_url == source_url

    fb_rec = contact_social.get_record("social.facebook")
    assert fb_rec.status == EvidenceStatus.FOUND
    assert fb_rec.value == "https://www.facebook.com/komorebibotanicals/"

    yt_rec = contact_social.get_record("social.youtube")
    assert yt_rec.status == EvidenceStatus.FOUND
    assert yt_rec.value == "https://www.youtube.com/@komorebi_plants"

    tw_rec = contact_social.get_record("social.twitter")
    assert tw_rec.status == EvidenceStatus.FOUND
    assert tw_rec.value == "https://x.com/komorebi_plants"

    li_rec = contact_social.get_record("social.linkedin")
    assert li_rec.status == EvidenceStatus.FOUND
    assert li_rec.value == "https://www.linkedin.com/company/komorebi-botanicals"


def test_fixture_negative_signals_no_fabrication():
    """7. Negative case: ordinary article page does not fabricate products, contacts, or platforms."""
    html = load_fixture("negative_signals.html")
    source_url = "https://hikingjournal.org/posts/cascades"

    # Products: none
    assert extract_products_json_ld(html, source_url=source_url) == []
    assert extract_products_dom(html, source_url=source_url) == []

    # Store: not an ecommerce store
    store_res = extract_store_details(html, source_url=source_url)
    assert store_res.get("store.about_text") is None
    assert store_res.get_record("store.about_text").status == EvidenceStatus.NOT_FOUND

    # Contact & Social: none
    cs_res = extract_contact_and_social(html, source_url=source_url)
    assert cs_res.get("contact.email") is None
    assert cs_res.get_record("contact.email").status == EvidenceStatus.NOT_FOUND
    assert cs_res.get("contact.phone") is None
    assert cs_res.get_record("contact.phone").status == EvidenceStatus.NOT_FOUND

    for platform in ("instagram", "facebook", "youtube", "twitter", "linkedin"):
        rec = cs_res.get_record(f"social.{platform}")
        assert rec.status == EvidenceStatus.NOT_FOUND
        assert rec.value is None

    # Platform Detector: not Shopify, WooCommerce, or Magento
    platform_res = detect_ecommerce_platform(html, source_url=source_url)
    assert platform_res.evidence.value is None
    assert platform_res.evidence.status == EvidenceStatus.NOT_FOUND
    assert platform_res.evidence.confidence == 1.0
    assert platform_res.matched_indicators == []


def test_crawl_record_integration_with_fixtures():
    """8. D2 CrawlRecord integration: processes accessible records and respects blocked state."""
    html_valid = load_fixture("product_valid_json_ld.html")

    # Accessible CrawlRecord
    accessible_record = CrawlRecordInput(
        source_url="https://teacraft.example.com/products/artisan-ceramic-teapot",
        canonical_url="https://teacraft.example.com/products/artisan-ceramic-teapot",
        page_type="product",
        rendered_html=html_valid,
        access_state="Accessible",
    )

    # JSON-LD extraction
    products = extract_products_json_ld(
        html=accessible_record.rendered_html,
        source_url=accessible_record.source_url,
    )
    assert len(products) == 1
    assert products[0].get("product.title") == "Artisan Ceramic Teapot"
    assert products[0].get_record("product.title").source_url == accessible_record.source_url

    # Blocked CrawlRecord
    blocked_record = CrawlRecordInput(
        source_url="https://teacraft.example.com/blocked",
        rendered_html=html_valid,
        access_state="Blocked",
    )
    from scraper_detection.extraction.dom_product_extractor import DOMProductExtractor
    dom_extractor = DOMProductExtractor()
    assert dom_extractor.extract_from_crawl_record(blocked_record) == []
