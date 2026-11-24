"""Unit tests for D3 Day 4 Store Details, Contact, and Social Profile Extractor.

All tests run completely offline without network requests and verify:
- store name from header/title
- About/Contact text
- normal business email
- mailto email
- phone/tel link
- noisy/invalid email text
- multiple phone formats
- Instagram
- Facebook
- YouTube
- X/Twitter
- LinkedIn
- relative social URL
- duplicate social links
- missing contact information
- page with no social links
- blocked/inaccessible CrawlRecord
- multiple CrawlRecords with different source URLs
"""

from datetime import datetime, timezone
import pytest

from scraper_detection.extraction.contact_social_extractor import (
    ContactSocialExtractor,
    extract_contact_and_social,
)
from scraper_detection.extraction.dom_product_extractor import CrawlRecordInput
from scraper_detection.extraction.store_extractor import (
    StoreExtractor,
    extract_store_details,
)
from scraper_detection.schemas.evidence import (
    EvidenceMethod,
    EvidenceStatus,
)


def test_store_name_from_header_and_title():
    # Case 1: From logo text in header
    html_header = """
    <html>
    <head><title>Home</title></head>
    <body>
        <header>
            <div class="site-header__logo">
                <a class="logo-text" href="/">Celestial Gems</a>
            </div>
        </header>
    </body>
    </html>
    """
    res1 = extract_store_details(html_header, source_url="https://example.com")
    rec1 = res1.get_record("store.name")
    assert rec1 is not None
    assert rec1.status == EvidenceStatus.FOUND
    assert rec1.value == "Celestial Gems"
    assert rec1.method == EvidenceMethod.DOM

    # Case 2: From title with separator
    html_title = """
    <html>
    <head>
        <title>Aura Living | Modern Sustainable Furniture</title>
    </head>
    <body></body>
    </html>
    """
    res2 = extract_store_details(html_title, source_url="https://auraliving.com")
    assert res2.get("store.name") == "Aura Living"

    # Case 3: From OpenGraph meta tag
    html_og = """
    <html>
    <head>
        <meta property="og:site_name" content="Kaveri Silks">
        <title>Home - Online Store</title>
    </head>
    <body></body>
    </html>
    """
    res3 = extract_store_details(html_og, source_url="https://kaverisilks.in")
    rec3 = res3.get_record("store.name")
    assert rec3.value == "Kaveri Silks"
    assert rec3.method == EvidenceMethod.META


def test_about_contact_text():
    html = """
    <html>
    <body>
        <section class="about-us">
            <h2>Our Story</h2>
            <p>Founded in 2018, we craft handcrafted leather goods designed to last a lifetime.</p>
            <form action="/subscribe"><input type="email" placeholder="Enter email" /></form>
            <button>Submit</button>
        </section>
    </body>
    </html>
    """
    res = extract_store_details(html, source_url="https://example.com/pages/about-us", page_type="about")
    about_rec = res.get_record("store.about_text")
    assert about_rec is not None
    assert about_rec.status == EvidenceStatus.FOUND
    assert "Founded in 2018" in about_rec.value
    assert "Enter email" not in about_rec.value  # Form inputs decomposed
    assert about_rec.method == EvidenceMethod.DOM


def test_normal_business_email():
    html = """
    <html>
    <body>
        <footer>
            <div class="footer-contact">
                <p>Have questions? Reach our customer team at care@nordicnord.com anytime.</p>
            </div>
        </footer>
    </body>
    </html>
    """
    res = extract_contact_and_social(html, source_url="https://nordicnord.com")
    rec = res.get_record("contact.email")
    assert rec is not None
    assert rec.status == EvidenceStatus.FOUND
    assert rec.value == "care@nordicnord.com"
    assert rec.method == EvidenceMethod.REGEX


def test_mailto_email():
    html = """
    <html>
    <body>
        <div class="contact-box">
            <a href="mailto:support@urbanthreads.co?subject=OrderInquiry">Email Customer Care</a>
        </div>
    </body>
    </html>
    """
    res = extract_contact_and_social(html, source_url="https://urbanthreads.co")
    rec = res.get_record("contact.email")
    assert rec is not None
    assert rec.status == EvidenceStatus.FOUND
    assert rec.value == "support@urbanthreads.co"
    assert rec.method == EvidenceMethod.DOM


def test_phone_tel_link():
    html = """
    <html>
    <body>
        <header>
            <a href="tel:+18005550199" class="phone-link">Call toll-free: 1-800-555-0199</a>
        </header>
    </body>
    </html>
    """
    res = extract_contact_and_social(html, source_url="https://example.com")
    rec = res.get_record("contact.phone")
    assert rec is not None
    assert rec.status == EvidenceStatus.FOUND
    assert rec.value == "+18005550199"
    assert rec.method == EvidenceMethod.DOM


def test_noisy_invalid_email_text():
    html = """
    <html>
    <body>
        <!-- Image asset mistaken for email by naive regex -->
        <img src="/assets/images/user-icon@2x.png" alt="icon" />
        <!-- Dummy/placeholder emails -->
        <p>Example: user@example.com or test@domain.com</p>
        <!-- Real business email -->
        <div class="contact-info">
            <p>For sales inquiries contact: sales@artisancraft.shop</p>
        </div>
    </body>
    </html>
    """
    res = extract_contact_and_social(html, source_url="https://artisancraft.shop")
    rec = res.get_record("contact.email")
    assert rec.status == EvidenceStatus.FOUND
    assert rec.value == "sales@artisancraft.shop"
    assert "user@example.com" not in rec.value
    assert "user-icon@2x.png" not in rec.value


def test_multiple_phone_formats():
    formats = [
        ("US Phone", "<p>Call our office: (555) 234-5678</p>", "(555) 234-5678"),
        ("Toll Free", "<p>Toll-free hotline: 1-800-555-0144</p>", "1-800-555-0144"),
        ("Indian Phone", "<p>Support Phone: +91 98765 43210</p>", "+91 98765 43210"),
        ("UK Phone", "<p>Customer Tel: +44 20 7946 0958</p>", "+44 20 7946 0958"),
    ]

    for label, snippet, expected in formats:
        html = f"<html><body><div class='contact'>{snippet}</div></body></html>"
        res = extract_contact_and_social(html, source_url="https://example.com")
        rec = res.get_record("contact.phone")
        assert rec is not None, f"Failed for {label}"
        assert rec.status == EvidenceStatus.FOUND, f"Not found for {label}"
        assert rec.value == expected, f"Value mismatch for {label}"


def test_social_instagram():
    html = """
    <html>
    <body>
        <footer>
            <!-- Post link (must be ignored) -->
            <a href="https://www.instagram.com/p/C123abc/">View Post</a>
            <!-- Profile link -->
            <a href="https://www.instagram.com/acme_atelier/">Follow on Instagram</a>
        </footer>
    </body>
    </html>
    """
    res = extract_contact_and_social(html, source_url="https://acme.com")
    rec = res.get_record("social.instagram")
    assert rec is not None
    assert rec.status == EvidenceStatus.FOUND
    assert rec.value == "https://www.instagram.com/acme_atelier/"


def test_social_facebook():
    html = """
    <html>
    <body>
        <!-- Share button (must be ignored) -->
        <a href="https://www.facebook.com/sharer/sharer.php?u=https://example.com">Share on FB</a>
        <!-- Official page link -->
        <a href="https://facebook.com/acmebrand">Like our Page</a>
    </body>
    </html>
    """
    res = extract_contact_and_social(html, source_url="https://acme.com")
    rec = res.get_record("social.facebook")
    assert rec is not None
    assert rec.status == EvidenceStatus.FOUND
    assert rec.value == "https://www.facebook.com/acmebrand/"


def test_social_youtube():
    html = """
    <html>
    <body>
        <!-- Video link (must be ignored) -->
        <a href="https://www.youtube.com/watch?v=dQw4w9WgXcQ">Watch Trailer</a>
        <!-- Channel link -->
        <a href="https://youtube.com/@acme_studios">Subscribe</a>
    </body>
    </html>
    """
    res = extract_contact_and_social(html, source_url="https://acme.com")
    rec = res.get_record("social.youtube")
    assert rec is not None
    assert rec.status == EvidenceStatus.FOUND
    assert rec.value == "https://www.youtube.com/@acme_studios"


def test_social_twitter():
    html = """
    <html>
    <body>
        <!-- Tweet intent link (must be ignored) -->
        <a href="https://twitter.com/intent/tweet?text=Hello">Share on Twitter</a>
        <!-- Profile link on x.com -->
        <a href="https://x.com/acme_official">Follow @acme_official</a>
    </body>
    </html>
    """
    res = extract_contact_and_social(html, source_url="https://acme.com")
    rec = res.get_record("social.twitter")
    assert rec is not None
    assert rec.status == EvidenceStatus.FOUND
    assert rec.value == "https://x.com/acme_official"


def test_social_linkedin():
    html = """
    <html>
    <body>
        <!-- Share link (must be ignored) -->
        <a href="https://www.linkedin.com/shareArticle?mini=true&url=https://example.com">Share Article</a>
        <!-- Company profile -->
        <a href="https://www.linkedin.com/company/acme-enterprises">LinkedIn Company</a>
    </body>
    </html>
    """
    res = extract_contact_and_social(html, source_url="https://acme.com")
    rec = res.get_record("social.linkedin")
    assert rec is not None
    assert rec.status == EvidenceStatus.FOUND
    assert rec.value == "https://www.linkedin.com/company/acme-enterprises"


def test_relative_social_url():
    # Protocol-relative URL //instagram.com/acme
    html = """
    <html>
    <body>
        <a href="//instagram.com/acmerelative">Instagram</a>
    </body>
    </html>
    """
    res = extract_contact_and_social(html, source_url="https://acme.com")
    rec = res.get_record("social.instagram")
    assert rec.status == EvidenceStatus.FOUND
    assert rec.value == "https://www.instagram.com/acmerelative/"


def test_duplicate_social_links():
    # Multiple links to same profile in header and footer
    html = """
    <html>
    <body>
        <header><a href="https://www.facebook.com/acmestore/">FB</a></header>
        <footer><a href="https://www.facebook.com/acmestore/">FB Footer</a></footer>
    </body>
    </html>
    """
    res = extract_contact_and_social(html, source_url="https://acme.com")
    rec = res.get_record("social.facebook")
    assert rec.status == EvidenceStatus.FOUND
    assert rec.value == "https://www.facebook.com/acmestore/"


def test_missing_contact_information():
    html = """
    <html>
    <body>
        <h1>Catalog Only</h1>
        <p>No phone, email, or social links are present on this page.</p>
    </body>
    </html>
    """
    res = extract_contact_and_social(html, source_url="https://example.com")

    email_rec = res.get_record("contact.email")
    assert email_rec.status == EvidenceStatus.NOT_OBSERVED
    assert email_rec.value is None

    phone_rec = res.get_record("contact.phone")
    assert phone_rec.status == EvidenceStatus.NOT_OBSERVED
    assert phone_rec.value is None


def test_page_with_no_social_links():
    html = """
    <html>
    <body>
        <a href="/catalog">Catalog</a>
        <a href="/login">Login</a>
        <a href="/cart">Cart</a>
    </body>
    </html>
    """
    res = extract_contact_and_social(html, source_url="https://example.com")
    for platform in ("instagram", "facebook", "youtube", "twitter", "linkedin"):
        rec = res.get_record(f"social.{platform}")
        assert rec.status == EvidenceStatus.NOT_OBSERVED
        assert rec.value is None


def test_blocked_inaccessible_crawl_record():
    blocked_record = CrawlRecordInput(
        source_url="https://example.com/contact",
        rendered_html="""
        <p>Email: contact@blockedstore.com</p>
        <a href="https://instagram.com/blocked">IG</a>
        """,
        access_state="Blocked",
    )
    extractor = ContactSocialExtractor()
    res = extractor.extract_from_crawl_record(blocked_record)

    # Inaccessible records return BLOCKED status and no extracted value
    for fld in res.records:
        assert res.records[fld].status == EvidenceStatus.BLOCKED
        assert res.records[fld].value is None


def test_multiple_crawl_records_aggregation():
    # Record 1: Homepage with store name and Instagram link
    rec1 = CrawlRecordInput(
        source_url="https://acme.com",
        page_type="homepage",
        rendered_html="""
        <html><head><title>Acme Crafts</title></head>
        <body>
            <header><h1>Acme Crafts</h1></header>
            <footer><a href="https://instagram.com/acmecrafts">IG</a></footer>
        </body></html>
        """,
        access_state="Accessible",
    )

    # Record 2: Contact page with email and phone
    rec2 = CrawlRecordInput(
        source_url="https://acme.com/pages/contact",
        page_type="contact",
        rendered_html="""
        <html><body>
            <div class="contact-details">
                <p>Email: support@acmecrafts.com</p>
                <p>Phone: +1 800 555 0188</p>
            </div>
        </body></html>
        """,
        access_state="Accessible",
    )

    # Record 3: About page with store about text
    rec3 = CrawlRecordInput(
        source_url="https://acme.com/pages/about",
        page_type="about",
        rendered_html="""
        <html><body>
            <section class="about-us">
                <p>Acme Crafts has been designing sustainable ceramic homeware since 2012.</p>
            </section>
        </body></html>
        """,
        access_state="Accessible",
    )

    # Aggregate store details across records
    store_ext = StoreExtractor()
    store_res = store_ext.extract_from_crawl_records([rec1, rec2, rec3])
    assert store_res.get("store.name") == "Acme Crafts"
    assert store_res.get_record("store.name").source_url == "https://acme.com"
    assert "sustainable ceramic homeware" in store_res.get("store.about_text")
    assert store_res.get_record("store.about_text").source_url == "https://acme.com/pages/about"

    # Aggregate contact/social across records
    contact_ext = ContactSocialExtractor()
    contact_res = contact_ext.extract_from_crawl_records([rec1, rec2, rec3])
    assert contact_res.get("contact.email") == "support@acmecrafts.com"
    assert contact_res.get_record("contact.email").source_url == "https://acme.com/pages/contact"
    assert contact_res.get("contact.phone") == "+1 800 555 0188"
    assert contact_res.get_record("contact.phone").source_url == "https://acme.com/pages/contact"
    assert contact_res.get("social.instagram") == "https://www.instagram.com/acmecrafts/"
    assert contact_res.get_record("social.instagram").source_url == "https://acme.com"
