"""Unit tests for D3 Day 2 JSON-LD Product Extractor.

All tests run completely offline without network requests and verify:
- normal Product JSON-LD
- Product with Offer
- multiple products
- @graph
- ItemList containing products
- ProductGroup
- malformed JSON-LD
- missing price
- missing currency
- multiple JSON-LD blocks
"""

from datetime import datetime, timezone
import pytest

from scraper_detection.extraction.product_extractor import (
    JSONLDProductExtractor,
    extract_products_json_ld,
)
from scraper_detection.schemas.evidence import (
    EvidenceMethod,
    EvidenceStatus,
)


def test_normal_product_json_ld():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "Classic Cotton Tee",
            "description": "Essential crewneck crafted from 100% organic cotton.",
            "url": "https://example.com/products/classic-tee"
        }
        </script>
    </head>
    <body><h1>Classic Cotton Tee</h1></body>
    </html>
    """
    products = extract_products_json_ld(html, source_url="https://example.com/products/classic-tee")
    assert len(products) == 1
    p = products[0]

    # Title
    title_rec = p.get_record("product.title")
    assert title_rec is not None
    assert title_rec.status == EvidenceStatus.FOUND
    assert title_rec.value == "Classic Cotton Tee"
    assert title_rec.method == EvidenceMethod.JSON_LD
    assert title_rec.confidence == 1.0

    # Description
    desc_rec = p.get_record("product.description")
    assert desc_rec is not None
    assert desc_rec.status == EvidenceStatus.FOUND
    assert desc_rec.value == "Essential crewneck crafted from 100% organic cotton."

    # URL
    url_rec = p.get_record("product.url")
    assert url_rec is not None
    assert url_rec.status == EvidenceStatus.FOUND
    assert url_rec.value == "https://example.com/products/classic-tee"

    # Price and currency should be NOT_FOUND without fabrication
    price_rec = p.get_record("product.price")
    assert price_rec is not None
    assert price_rec.status == EvidenceStatus.NOT_FOUND
    assert price_rec.value is None


def test_product_with_offer():
    html = """
    <html>
    <head>
        <script type="application/ld+json">
        {
            "@context": "https://schema.org/",
            "@type": "Product",
            "name": "Wireless Noise Cancelling Headphones",
            "url": "/products/headphones",
            "description": "Premium over-ear wireless headphones.",
            "offers": {
                "@type": "Offer",
                "price": "199.99",
                "priceCurrency": "USD",
                "availability": "https://schema.org/InStock",
                "priceSpecification": [
                    {
                        "@type": "UnitPriceSpecification",
                        "priceType": "https://schema.org/ListPrice",
                        "price": "249.99"
                    },
                    {
                        "@type": "UnitPriceSpecification",
                        "priceType": "https://schema.org/SalePrice",
                        "price": "199.99"
                    }
                ]
            }
        }
        </script>
    </head>
    </html>
    """
    products = extract_products_json_ld(html, source_url="https://audio-store.com/item")
    assert len(products) == 1
    p = products[0]

    assert p.get("product.title") == "Wireless Noise Cancelling Headphones"
    # Relative URL resolved against source_url
    assert p.get("product.url") == "https://audio-store.com/products/headphones"
    assert p.get("product.price") == 199.99
    assert p.get("product.currency") == "USD"
    assert p.get("product.availability") == "https://schema.org/InStock"
    assert p.get("product.original_price") == 249.99
    assert p.get("product.discount_price") == 199.99


def test_multiple_products_in_array():
    html = """
    <html>
    <head>
        <script type="application/ld+json">
        [
            {
                "@type": "Product",
                "name": "Leather Boots",
                "offers": {"price": "120.00", "priceCurrency": "EUR"}
            },
            {
                "@type": "Product",
                "name": "Wool Socks",
                "offers": {"price": "15.00", "priceCurrency": "EUR"}
            }
        ]
        </script>
    </head>
    </html>
    """
    products = extract_products_json_ld(html, source_url="https://boots-store.com")
    assert len(products) == 2

    assert products[0].get("product.title") == "Leather Boots"
    assert products[0].get("product.price") == 120.0
    assert products[0].get("product.currency") == "EUR"

    assert products[1].get("product.title") == "Wool Socks"
    assert products[1].get("product.price") == 15.0
    assert products[1].get("product.currency") == "EUR"


def test_graph_json_ld():
    html = """
    <html>
    <head>
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@graph": [
                {
                    "@type": "WebSite",
                    "name": "Demo E-Commerce"
                },
                {
                    "@type": "Organization",
                    "name": "Demo Corp"
                },
                {
                    "@type": "Product",
                    "name": "Solar Powered Watch",
                    "description": "Eco-friendly timepiece",
                    "offers": {
                        "@type": "Offer",
                        "price": 350,
                        "priceCurrency": "GBP",
                        "availability": "https://schema.org/InStock"
                    }
                }
            ]
        }
        </script>
    </head>
    </html>
    """
    products = extract_products_json_ld(html)
    assert len(products) == 1
    p = products[0]
    assert p.get("product.title") == "Solar Powered Watch"
    assert p.get("product.price") == 350.0
    assert p.get("product.currency") == "GBP"


def test_item_list_containing_products():
    html = """
    <html>
    <head>
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@type": "ItemList",
            "name": "Top Sellers",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": 1,
                    "item": {
                        "@type": "Product",
                        "name": "Item Alpha",
                        "offers": {"price": "10.50", "priceCurrency": "USD"}
                    }
                },
                {
                    "@type": "ListItem",
                    "position": 2,
                    "item": {
                        "@type": "Product",
                        "name": "Item Beta",
                        "offers": {"price": "22.00", "priceCurrency": "USD"}
                    }
                }
            ]
        }
        </script>
    </head>
    </html>
    """
    products = extract_products_json_ld(html)
    assert len(products) == 2
    assert products[0].get("product.title") == "Item Alpha"
    assert products[0].get("product.price") == 10.50
    assert products[1].get("product.title") == "Item Beta"
    assert products[1].get("product.price") == 22.00


def test_product_group_with_variants():
    html = """
    <html>
    <head>
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@type": "ProductGroup",
            "name": "Performance Running Shoes",
            "description": "Engineered for marathon training.",
            "url": "https://example.com/shoes",
            "hasVariant": [
                {
                    "@type": "Product",
                    "name": "Performance Running Shoes - Midnight Black",
                    "offers": {
                        "price": "140.00",
                        "priceCurrency": "USD",
                        "availability": "InStock"
                    }
                },
                {
                    "@type": "Product",
                    "offers": {
                        "price": "145.00",
                        "priceCurrency": "USD"
                    }
                }
            ]
        }
        </script>
    </head>
    </html>
    """
    products = extract_products_json_ld(html)
    assert len(products) == 2

    # Variant 1 has specific name
    assert products[0].get("product.title") == "Performance Running Shoes - Midnight Black"
    assert products[0].get("product.price") == 140.00
    assert products[0].get("product.description") == "Engineered for marathon training."

    # Variant 2 inherits group name and description
    assert products[1].get("product.title") == "Performance Running Shoes"
    assert products[1].get("product.price") == 145.00
    assert products[1].get("product.description") == "Engineered for marathon training."


def test_malformed_json_ld_handling():
    html = """
    <html>
    <head>
        <!-- Malformed JSON block -->
        <script type="application/ld+json">
        {
            "name": "Corrupt JSON",
            "unquoted_key": incomplete,
        </script>
        <!-- Empty script block -->
        <script type="application/ld+json"></script>
        <!-- Whitespace only block -->
        <script type="application/ld+json">
           
        </script>
    </head>
    <body>No crash</body>
    </html>
    """
    # Safe handling: should gracefully skip malformed / empty blocks and return empty list
    products = extract_products_json_ld(html)
    assert products == []


def test_missing_price():
    html = """
    <html>
    <head>
        <script type="application/ld+json">
        {
            "@type": "Product",
            "name": "Custom Handmade Mug",
            "description": "Ceramic hand-thrown mug."
        }
        </script>
    </head>
    </html>
    """
    products = extract_products_json_ld(html)
    assert len(products) == 1
    p = products[0]

    assert p.get("product.title") == "Custom Handmade Mug"
    price_rec = p.get_record("product.price")
    assert price_rec.status == EvidenceStatus.NOT_FOUND
    assert price_rec.value is None


def test_missing_currency():
    html = """
    <html>
    <head>
        <script type="application/ld+json">
        {
            "@type": "Product",
            "name": "Vintage Postcard",
            "offers": {
                "@type": "Offer",
                "price": "5.00"
            }
        }
        </script>
    </head>
    </html>
    """
    products = extract_products_json_ld(html)
    assert len(products) == 1
    p = products[0]

    price_rec = p.get_record("product.price")
    assert price_rec.status == EvidenceStatus.FOUND
    assert price_rec.value == 5.0

    curr_rec = p.get_record("product.currency")
    assert curr_rec.status == EvidenceStatus.NOT_FOUND
    assert curr_rec.value is None


def test_multiple_json_ld_blocks():
    html = """
    <html>
    <head>
        <!-- Block 1: Valid product -->
        <script type="application/ld+json">
        {
            "@type": "Product",
            "name": "Product From Block 1",
            "offers": {"price": 25.0, "priceCurrency": "USD"}
        }
        </script>
        <!-- Block 2: Broken script -->
        <script type="application/ld+json">
            { broken: json ...
        </script>
        <!-- Block 3: Another valid product -->
        <script type="application/ld+json">
        {
            "@type": "Product",
            "name": "Product From Block 3",
            "offers": {"price": 75.0, "priceCurrency": "USD"}
        }
        </script>
    </head>
    </html>
    """
    products = extract_products_json_ld(html)
    assert len(products) == 2
    titles = [p.get("product.title") for p in products]
    assert "Product From Block 1" in titles
    assert "Product From Block 3" in titles
