"""Deterministic page discovery and selection logic.

Selects:
- Homepage
- Up to 2 collection/category pages
- Up to 2 product pages
- About page
- Contact page
"""

import re
from urllib.parse import urlparse, urljoin
from browser_automation.bundle import PageType
from browser_automation.policy import normalize_url, get_origin
from browser_automation.logging import logger


COLLECTION_PATTERNS = [
    re.compile(r"/collections?/", re.I),
    re.compile(r"/category/", re.I),
    re.compile(r"/categories/", re.I),
    re.compile(r"/shop/", re.I),
    re.compile(r"/catalog/", re.I),
]

PRODUCT_PATTERNS = [
    re.compile(r"/products?/", re.I),
    re.compile(r"/item/", re.I),
    re.compile(r"/p/[a-zA-Z0-9_-]+", re.I),
    re.compile(r"/dp/[a-zA-Z0-9]+", re.I),
]

ABOUT_PATTERNS = [
    re.compile(r"/about(-us)?/?$", re.I),
    re.compile(r"/pages/about(-us)?/?$", re.I),
    re.compile(r"/our-story/?$", re.I),
    re.compile(r"/who-we-are/?$", re.I),
]

CONTACT_PATTERNS = [
    re.compile(r"/contact(-us)?/?$", re.I),
    re.compile(r"/pages/contact(-us)?/?$", re.I),
    re.compile(r"/support/?$", re.I),
    re.compile(r"/help/contact/?$", re.I),
]


def classify_page_type(url: str, base_url: str) -> PageType:
    """Classify semantic page type based on URL path patterns."""
    norm_url = normalize_url(url)
    norm_base = normalize_url(base_url)

    if norm_url == norm_base or urlparse(norm_url).path in ("", "/"):
        return PageType.HOMEPAGE

    path = urlparse(norm_url).path

    for pat in ABOUT_PATTERNS:
        if pat.search(path):
            return PageType.ABOUT

    for pat in CONTACT_PATTERNS:
        if pat.search(path):
            return PageType.CONTACT

    for pat in PRODUCT_PATTERNS:
        if pat.search(path):
            return PageType.PRODUCT

    for pat in COLLECTION_PATTERNS:
        if pat.search(path):
            return PageType.COLLECTION

    return PageType.OTHER


def discover_and_select_pages(
    base_url: str,
    extracted_links: list[str],
    max_pages: int = 7,
) -> tuple[list[tuple[str, PageType]], list[str], list[dict[str, str]]]:
    """Deterministically filter and prioritize discovered links.

    Returns:
    - selected: list of (canonical_url, page_type)
    - discovered_all: list of all normalized valid URLs
    - skipped: list of {"url": ..., "reason": ...}
    """
    base_origin = get_origin(base_url)
    homepage_norm = normalize_url(base_url)

    discovered_all: set[str] = set()
    skipped: list[dict[str, str]] = []

    categorized: dict[PageType, list[str]] = {
        PageType.HOMEPAGE: [homepage_norm],
        PageType.COLLECTION: [],
        PageType.PRODUCT: [],
        PageType.ABOUT: [],
        PageType.CONTACT: [],
        PageType.OTHER: [],
    }

    discovered_all.add(homepage_norm)

    for raw_link in extracted_links:
        if not raw_link or raw_link.startswith("#") or raw_link.startswith("javascript:") or raw_link.startswith("mailto:") or raw_link.startswith("tel:"):
            continue

        resolved = urljoin(base_url, raw_link)
        link_origin = get_origin(resolved)

        if link_origin != base_origin:
            skipped.append({"url": resolved, "reason": "Cross-origin link disallowed by same-site policy"})
            continue

        norm = normalize_url(resolved)
        discovered_all.add(norm)

        if norm == homepage_norm:
            continue

        ptype = classify_page_type(norm, base_url)
        if norm not in categorized[ptype]:
            categorized[ptype].append(norm)

    # Sort deterministically within each category
    for ptype in categorized:
        categorized[ptype].sort()

    selected: list[tuple[str, PageType]] = []
    # 1. Homepage (always selected)
    selected.append((homepage_norm, PageType.HOMEPAGE))

    # 2. Maximum 2 Collection pages
    for col_url in categorized[PageType.COLLECTION][:2]:
        selected.append((col_url, PageType.COLLECTION))
    for skipped_col in categorized[PageType.COLLECTION][2:]:
        skipped.append({"url": skipped_col, "reason": "Exceeded max collection quota (limit 2)"})

    # 3. Maximum 2 Product pages
    for prod_url in categorized[PageType.PRODUCT][:2]:
        selected.append((prod_url, PageType.PRODUCT))
    for skipped_prod in categorized[PageType.PRODUCT][2:]:
        skipped.append({"url": skipped_prod, "reason": "Exceeded max product quota (limit 2)"})

    # 4. About page (up to 1)
    if categorized[PageType.ABOUT]:
        selected.append((categorized[PageType.ABOUT][0], PageType.ABOUT))
        for skipped_about in categorized[PageType.ABOUT][1:]:
            skipped.append({"url": skipped_about, "reason": "Exceeded about quota (limit 1)"})

    # 5. Contact page (up to 1)
    if categorized[PageType.CONTACT]:
        selected.append((categorized[PageType.CONTACT][0], PageType.CONTACT))
        for skipped_contact in categorized[PageType.CONTACT][1:]:
            skipped.append({"url": skipped_contact, "reason": "Exceeded contact quota (limit 1)"})

    # Enforce overall max_pages
    final_selected = selected[:max_pages]
    for over_quota in selected[max_pages:]:
        skipped.append({"url": over_quota[0], "reason": f"Exceeded crawl max_pages budget ({max_pages})"})

    return final_selected, sorted(list(discovered_all)), skipped
