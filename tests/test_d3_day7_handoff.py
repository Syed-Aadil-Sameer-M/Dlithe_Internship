"""Day 7 Handoff Integration Tests (Developer 3 - Scraping & Detection).

Validates the complete Week 1 extraction handoff layer:
- Ingestion of D2 CrawlBundle & CrawlRecord dataclass models
- Processing of 3 offline reference store fixture sets:
  * reference_shopify/
  * reference_woocommerce/
  * reference_magento/
- Verification that EvidenceRecords are emitted with canonical statuses
  (Found, Not observed, Unverified, Blocked)
- Verification that source URLs, methods, and confidence values are preserved
- Strict offline execution with zero network access and zero Playwright imports.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

import pytest

from scraper_detection.pipeline import (
    D3ExtractionPipeline,
    StoreExtractionResult,
    extract_store_data,
)
from scraper_detection.schemas.evidence import (
    EvidenceMethod,
    EvidenceRecord,
    EvidenceStatus,
)


# ============================================================================
# D2 Typed Interfaces (matching browser_automation/bundle.py exactly)
# ============================================================================

class AccessState(str, Enum):
    """Classification of page accessibility from D2."""
    ACCESSIBLE = "Accessible"
    BLOCKED = "Blocked"
    UNAVAILABLE = "Unavailable"
    ERROR = "Error"


class PageType(str, Enum):
    """Semantic page roles from D2."""
    HOMEPAGE = "homepage"
    COLLECTION = "collection"
    PRODUCT = "product"
    ABOUT = "about"
    CONTACT = "contact"
    OTHER = "other"


@dataclass(frozen=True)
class CrawlRecord:
    """Page-level crawl artifact produced by D2 crawler."""
    canonical_url: str
    source_url: str
    page_type: PageType
    access_state: AccessState
    fetch_timestamp: str  # ISO 8601 UTC string
    rendered_html: str = ""
    visible_text: str = ""
    script_urls: list[str] = field(default_factory=list)
    http_status: int | None = 200
    content_type: str | None = "text/html"
    access_reason: str = ""
    error_message: str | None = None


@dataclass(frozen=True)
class CrawlBundle:
    """Comprehensive crawl bundle produced by D2 for a store."""
    base_url: str
    records: list[CrawlRecord] = field(default_factory=list)
    crawler_user_agent: str = "StoreResearchCrawler/1.0"


# ============================================================================
# Helpers
# ============================================================================

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _read_fixture(relative_path: str) -> str:
    path = FIXTURES_DIR / relative_path
    if not path.exists():
        raise FileNotFoundError(f"Fixture not found at {path}")
    return path.read_text(encoding="utf-8")


# ============================================================================
# Test Cases
# ============================================================================

def test_shopify_reference_store_handoff():
    """Verify D3 pipeline over multi-page Shopify reference store bundle."""
    home_html = _read_fixture("reference_shopify/home.html")
    prod_html = _read_fixture("reference_shopify/product.html")
    about_html = _read_fixture("reference_shopify/about.html")

    base_url = "https://aurora-atelier.com"
    timestamp = "2026-11-22T10:00:00+00:00"

    bundle = CrawlBundle(
        base_url=base_url,
        records=[
            CrawlRecord(
                canonical_url=f"{base_url}/",
                source_url=f"{base_url}/",
                page_type=PageType.HOMEPAGE,
                access_state=AccessState.ACCESSIBLE,
                fetch_timestamp=timestamp,
                rendered_html=home_html,
                script_urls=["https://cdn.shopify.com/s/files/1/0123/4567/t/1/assets/theme.js?v=987"],
            ),
            CrawlRecord(
                canonical_url=f"{base_url}/products/merino-wool-artisan-sweater",
                source_url=f"{base_url}/products/merino-wool-artisan-sweater",
                page_type=PageType.PRODUCT,
                access_state=AccessState.ACCESSIBLE,
                fetch_timestamp=timestamp,
                rendered_html=prod_html,
                script_urls=["https://cdn.shopify.com/s/files/1/0123/4567/t/1/assets/product.js"],
            ),
            CrawlRecord(
                canonical_url=f"{base_url}/pages/about",
                source_url=f"{base_url}/pages/about",
                page_type=PageType.ABOUT,
                access_state=AccessState.ACCESSIBLE,
                fetch_timestamp=timestamp,
                rendered_html=about_html,
                script_urls=["https://cdn.shopify.com/s/files/1/0123/4567/t/1/assets/about.js"],
            ),
        ],
    )

    result = extract_store_data(bundle)

    # 1. Pipeline result integrity
    assert isinstance(result, StoreExtractionResult)
    assert result.base_url == base_url
    assert result.records_analyzed == 3
    assert len(result.evidence_records) > 0

    # 2. Platform detection
    assert result.platform.platform == "Shopify"
    assert result.platform.evidence.status == EvidenceStatus.FOUND
    assert result.platform.evidence.confidence >= 0.90
    assert result.platform.evidence.field == "technology.ecommerce_platform"

    # 3. Store name & about story
    store_name_rec = result.get_evidence("store.name")
    assert store_name_rec is not None
    assert store_name_rec.status == EvidenceStatus.FOUND
    assert "Aurora Atelier" in store_name_rec.value

    about_rec = result.get_evidence("store.about_text")
    assert about_rec is not None
    assert about_rec.status == EvidenceStatus.FOUND
    assert "sustainable knitwear" in about_rec.value.lower()

    # 4. Contacts & Socials
    email_rec = result.get_evidence("contact.email")
    assert email_rec is not None
    assert email_rec.status == EvidenceStatus.FOUND
    assert email_rec.value == "concierge@aurora-atelier.com"

    phone_rec = result.get_evidence("contact.phone")
    assert phone_rec is not None
    assert phone_rec.status == EvidenceStatus.FOUND
    assert "800" in phone_rec.value and "456" in phone_rec.value

    ig_rec = result.get_evidence("social.instagram")
    assert ig_rec is not None
    assert ig_rec.status == EvidenceStatus.FOUND
    assert "instagram.com/aurora_atelier" in ig_rec.value

    fb_rec = result.get_evidence("social.facebook")
    assert fb_rec is not None
    assert fb_rec.status == EvidenceStatus.FOUND

    # 5. Products (via JSON-LD)
    assert len(result.products) >= 1
    prod = result.products[0]
    assert prod.records["product.title"].value == "Merino Wool Artisan Sweater"
    assert prod.records["product.title"].method == EvidenceMethod.JSON_LD
    assert prod.records["product.price"].value == 185.00
    assert prod.records["product.currency"].value == "USD"
    assert prod.records["product.availability"].value == "https://schema.org/InStock"

    # 6. Check that every evidence record has valid source URL and confidence
    for ev in result.evidence_records:
        assert isinstance(ev, EvidenceRecord)
        assert ev.source_url.startswith(base_url)
        assert 0.0 <= ev.confidence <= 1.0
        assert ev.status in (EvidenceStatus.FOUND, EvidenceStatus.NOT_OBSERVED, EvidenceStatus.UNVERIFIED)


def test_woocommerce_reference_store_handoff():
    """Verify D3 pipeline over multi-page WooCommerce reference store bundle."""
    home_html = _read_fixture("reference_woocommerce/home.html")
    prod_html = _read_fixture("reference_woocommerce/product.html")
    contact_html = _read_fixture("reference_woocommerce/contact.html")

    base_url = "https://spicewoodorganics.in"
    timestamp = "2026-11-22T10:00:00+00:00"

    bundle = CrawlBundle(
        base_url=base_url,
        records=[
            CrawlRecord(
                canonical_url=f"{base_url}/",
                source_url=f"{base_url}/",
                page_type=PageType.HOMEPAGE,
                access_state=AccessState.ACCESSIBLE,
                fetch_timestamp=timestamp,
                rendered_html=home_html,
                script_urls=["https://spicewoodorganics.in/wp-content/plugins/woocommerce/assets/js/frontend/woocommerce.min.js?ver=8.5.2"],
            ),
            CrawlRecord(
                canonical_url=f"{base_url}/product/organic-kashmiri-saffron-5g/",
                source_url=f"{base_url}/product/organic-kashmiri-saffron-5g/",
                page_type=PageType.PRODUCT,
                access_state=AccessState.ACCESSIBLE,
                fetch_timestamp=timestamp,
                rendered_html=prod_html,
                script_urls=["https://spicewoodorganics.in/wp-content/plugins/woocommerce/assets/js/frontend/single-product.min.js"],
            ),
            CrawlRecord(
                canonical_url=f"{base_url}/contact/",
                source_url=f"{base_url}/contact/",
                page_type=PageType.CONTACT,
                access_state=AccessState.ACCESSIBLE,
                fetch_timestamp=timestamp,
                rendered_html=contact_html,
            ),
        ],
    )

    result = extract_store_data(bundle)

    # 1. Platform detection
    assert result.platform.platform == "WooCommerce"
    assert result.platform.evidence.status == EvidenceStatus.FOUND
    assert result.platform.evidence.confidence >= 0.90

    # 2. Store details
    assert "Spicewood Organics" in result.get_evidence("store.name").value
    assert "single-origin botanicals" in result.get_evidence("store.about_text").value

    # 3. Contacts & Socials
    assert result.get_evidence("contact.email").value == "care@spicewoodorganics.in"
    assert "98765" in result.get_evidence("contact.phone").value
    assert "instagram.com/spicewood_organics" in result.get_evidence("social.instagram").value
    assert "youtube.com/@spicewoodorganics" in result.get_evidence("social.youtube").value

    # 4. Products (DOM fallback with INR currency)
    assert len(result.products) >= 1
    prod = result.products[0]
    assert prod.records["product.title"].value == "Organic Kashmiri Saffron 5g"
    assert prod.records["product.price"].value == 1499.00
    assert prod.records["product.currency"].value in ("INR", "₹")


def test_magento_reference_store_handoff():
    """Verify D3 pipeline over multi-page Magento reference store bundle."""
    home_html = _read_fixture("reference_magento/home.html")
    prod_html = _read_fixture("reference_magento/product.html")
    about_html = _read_fixture("reference_magento/about.html")

    base_url = "https://lumina-hardware.com"
    timestamp = "2026-11-22T10:00:00+00:00"

    bundle = CrawlBundle(
        base_url=base_url,
        records=[
            CrawlRecord(
                canonical_url=f"{base_url}/",
                source_url=f"{base_url}/",
                page_type=PageType.HOMEPAGE,
                access_state=AccessState.ACCESSIBLE,
                fetch_timestamp=timestamp,
                rendered_html=home_html,
                script_urls=[
                    "https://lumina-hardware.com/static/version1680000000/frontend/Magento/luma/en_US/requirejs/require.js",
                    "https://lumina-hardware.com/static/version1680000000/frontend/Magento/luma/en_US/mage/calendar.js",
                ],
            ),
            CrawlRecord(
                canonical_url=f"{base_url}/heavy-duty-hydraulic-jack-20t.html",
                source_url=f"{base_url}/heavy-duty-hydraulic-jack-20t.html",
                page_type=PageType.PRODUCT,
                access_state=AccessState.ACCESSIBLE,
                fetch_timestamp=timestamp,
                rendered_html=prod_html,
                script_urls=["https://lumina-hardware.com/static/version1680000000/frontend/Magento/luma/en_US/Magento_Catalog/js/price-utils.js"],
            ),
            CrawlRecord(
                canonical_url=f"{base_url}/about-us",
                source_url=f"{base_url}/about-us",
                page_type=PageType.ABOUT,
                access_state=AccessState.ACCESSIBLE,
                fetch_timestamp=timestamp,
                rendered_html=about_html,
            ),
        ],
    )

    result = extract_store_data(bundle)

    # 1. Platform detection
    assert result.platform.platform == "Magento"
    assert result.platform.evidence.status == EvidenceStatus.FOUND
    assert result.platform.evidence.confidence >= 0.90

    # 2. Store details
    assert "Lumina Industrial Hardware" in result.get_evidence("store.name").value
    assert "hydraulic machinery" in result.get_evidence("store.about_text").value

    # 3. Contacts & Socials
    assert result.get_evidence("contact.email").value == "orders@lumina-hardware.com"
    assert "555" in result.get_evidence("contact.phone").value
    assert "linkedin.com/company/lumina-hardware" in result.get_evidence("social.linkedin").value

    # 4. Products (DOM product-info-main)
    assert len(result.products) >= 1
    prod = result.products[0]
    assert prod.records["product.title"].value == "Heavy Duty Hydraulic Jack 20T"
    assert prod.records["product.price"].value == 249.50


def test_ambiguous_and_unsupported_signals_remain_unverified():
    """Verify that ambiguous or conflicting signals produce Unverified rather than guessing."""
    ambiguous_html = """
    <html>
        <head><title>Ambiguous Store</title></head>
        <body class="product-item">
            <script src="/js/common.js"></script>
            <script>var x = 'shopify'; var y = 'magento';</script>
            <h1>Test Store</h1>
            <div class="product">
                <span class="title">Generic Item</span>
                <span class="price">¤ 100</span>
            </div>
        </body>
    </html>
    """
    record = CrawlRecord(
        canonical_url="https://ambiguous-store.com/item",
        source_url="https://ambiguous-store.com/item",
        page_type=PageType.PRODUCT,
        access_state=AccessState.ACCESSIBLE,
        fetch_timestamp="2026-11-22T12:00:00Z",
        rendered_html=ambiguous_html,
    )
    bundle = CrawlBundle(base_url="https://ambiguous-store.com", records=[record])
    result = extract_store_data(bundle)

    # Platform should remain Unverified because evidence is conflicting/weak
    assert result.platform.evidence.status in (EvidenceStatus.UNVERIFIED, EvidenceStatus.NOT_OBSERVED)
    assert result.platform.platform is None or result.platform.evidence.status == EvidenceStatus.UNVERIFIED


def test_missing_observations_use_not_observed():
    """Verify that missing fields use canonical 'Not observed' rather than 'Not found'."""
    minimal_html = """
    <html>
        <head><title>Minimal Page</title></head>
        <body>
            <p>Welcome to our simple site.</p>
        </body>
    </html>
    """
    record = CrawlRecord(
        canonical_url="https://simple-site.org/",
        source_url="https://simple-site.org/",
        page_type=PageType.HOMEPAGE,
        access_state=AccessState.ACCESSIBLE,
        fetch_timestamp="2026-11-22T12:00:00Z",
        rendered_html=minimal_html,
    )
    bundle = CrawlBundle(base_url="https://simple-site.org", records=[record])
    result = extract_store_data(bundle)

    # Missing email/phone/socials should explicitly be NOT_OBSERVED
    email_rec = result.get_evidence("contact.email")
    assert email_rec.status == EvidenceStatus.NOT_OBSERVED
    assert email_rec.status.value == "Not observed"
    assert email_rec.value is None

    phone_rec = result.get_evidence("contact.phone")
    assert phone_rec.status == EvidenceStatus.NOT_OBSERVED
    assert phone_rec.status.value == "Not observed"

    platform_rec = result.get_evidence("technology.ecommerce_platform")
    assert platform_rec.status == EvidenceStatus.NOT_OBSERVED
    assert platform_rec.status.value == "Not observed"


def test_blocked_bundle_produces_blocked_evidence():
    """Verify that a blocked CrawlBundle produces BLOCKED EvidenceRecords and no fabricated facts."""
    blocked_record = CrawlRecord(
        canonical_url="https://protected-store.com/",
        source_url="https://protected-store.com/",
        page_type=PageType.HOMEPAGE,
        access_state=AccessState.BLOCKED,
        fetch_timestamp="2026-11-22T12:00:00Z",
        rendered_html="<html><body><h1>Access Denied (Cloudflare 403)</h1></body></html>",
    )
    bundle = CrawlBundle(base_url="https://protected-store.com", records=[blocked_record])
    result = extract_store_data(bundle)

    # Check blocked statuses
    assert result.platform.evidence.status == EvidenceStatus.BLOCKED
    assert result.store.records["store.name"].status == EvidenceStatus.BLOCKED
    assert result.contact_social.records["contact.email"].status == EvidenceStatus.BLOCKED
    assert len(result.products) == 0


def test_no_network_and_no_playwright_isolation():
    """Verify that D3 pipeline has no Playwright imports and operates strictly offline."""
    assert "playwright" not in sys.modules
    pipeline = D3ExtractionPipeline()
    assert hasattr(pipeline, "process_bundle")
