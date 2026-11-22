"""DOM Product Card Fallback Extractor (Developer 3 - Scraping & Detection).

Deterministic extraction of product metadata from HTML product cards and DOM elements
when JSON-LD structured data is absent, partial, or fallback parsing is required.
Strictly adheres to the EvidenceRecord contract and never fabricates missing fields.
Compatible with D2 CrawlRecord and CrawlBundle models.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Sequence
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from scraper_detection.extraction.product_extractor import (
    ExtractedProduct,
    SUPPORTED_PRODUCT_FIELDS,
)
from scraper_detection.schemas.evidence import (
    EvidenceMethod,
    EvidenceRecord,
    EvidenceStatus,
)

# Common product card container selectors across e-commerce platforms and standards
PRODUCT_CARD_SELECTORS: tuple[str, ...] = (
    '[itemtype*="schema.org/Product"]',
    '[class*="product-card"]',
    '[class*="product-item"]',
    '[class*="product_card"]',
    '[class*="product_item"]',
    '[class*="productCard"]',
    '[class*="productItem"]',
    '[class*="product-grid-item"]',
    '[class*="grid-product"]',
    '[class*="product-box"]',
    '[class*="product-tile"]',
    '[class*="product-teaser"]',
    '[class*="product-entry"]',
    '[class*="woocommerce-loop-product"]',
    '[class*="card-product"]',
    '[data-product-id]',
    '[data-product]',
    "article.product",
    "li.product",
)

# Selectors likely to contain product titles within a card
TITLE_SELECTORS: tuple[str, ...] = (
    '[class*="product-title"]',
    '[class*="product__title"]',
    '[class*="product_title"]',
    '[class*="card__title"]',
    '[class*="card-title"]',
    '[class*="item-title"]',
    '[class*="product-name"]',
    '[class*="product__name"]',
    '[itemprop="name"]',
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
)

# Selectors likely to contain price elements
PRICE_SELECTORS: tuple[str, ...] = (
    '[class*="price"]',
    '[class*="amount"]',
    '[class*="money"]',
    '[itemprop="price"]',
    '[data-price]',
)

# Known explicit currency mappings (symbol / code -> ISO-4217 code)
KNOWN_CURRENCIES: dict[str, str] = {
    "₹": "INR",
    "INR": "INR",
    "RS": "INR",
    "RS.": "INR",
    "$": "USD",
    "USD": "USD",
    "C$": "CAD",
    "CAD": "CAD",
    "A$": "AUD",
    "AUD": "AUD",
    "NZ$": "NZD",
    "NZD": "NZD",
    "€": "EUR",
    "EUR": "EUR",
    "£": "GBP",
    "GBP": "GBP",
    "¥": "JPY",
    "JPY": "JPY",
}

# Known ambiguous currency notations that cannot be reliably mapped to a single ISO code
AMBIGUOUS_CURRENCIES: set[str] = {
    "KR",
    "KR.",
    "ZŁ",
    "FT",
    "KČ",
    "R$",
    "¤",
    "PTS",
    "FR",
    "FR.",
}

# Non-product navigation or call-to-action phrases to reject as titles
IGNORED_TITLE_PHRASES: set[str] = {
    "quick view",
    "quick shop",
    "add to cart",
    "buy now",
    "view details",
    "view product",
    "sale",
    "new",
    "out of stock",
    "sold out",
    "in stock",
    "select options",
}


def normalize_whitespace(text: str | None) -> str:
    """Collapse whitespace sequences (spaces, tabs, newlines) and trim edges."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def parse_clean_float(num_str: str) -> float | None:
    """Deterministically parse integer or decimal numbers with European or Indian separators."""
    if not num_str or not num_str.strip():
        return None

    cleaned = num_str.strip().replace(" ", "")

    # Case 1: Both dot and comma present (e.g. '1,299.50' vs '1.299,50')
    if "." in cleaned and "," in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            # European format: dot is thousands separator, comma is decimal point
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            # Standard format: comma is thousands separator, dot is decimal point
            cleaned = cleaned.replace(",", "")
    # Case 2: Only comma present (e.g. '1,299' vs '49,90' vs '1,00,000')
    elif "," in cleaned:
        parts = cleaned.split(",")
        # If there's exactly one comma and exactly 2 decimal digits at end, it's a European decimal
        if len(parts) == 2 and len(parts[1]) == 2:
            cleaned = f"{parts[0]}.{parts[1]}"
        else:
            # Thousands separators (e.g. '1,299' or Indian numbering '1,00,000')
            cleaned = cleaned.replace(",", "")

    # Strip any dangling punctuation
    cleaned = cleaned.rstrip(".,")

    try:
        return float(cleaned)
    except (ValueError, OverflowError):
        return None


def normalize_price_and_currency(
    price_text: str | None,
    page_currency: str | None = None,
) -> tuple[float | None, str | None, EvidenceStatus]:
    """Parse numeric price and currency deterministically without guessing.

    Returns:
        tuple of (numeric_price, currency_code_or_notation, currency_evidence_status)
    """
    if not price_text or not price_text.strip():
        return None, None, EvidenceStatus.NOT_FOUND

    clean_text = normalize_whitespace(price_text)

    # Detect currency symbols or tokens in the text
    detected_currency: str | None = None
    currency_status = EvidenceStatus.NOT_FOUND

    # 1. Match symbol or explicit currency token
    token_pattern = (
        r"(?:₹|INR|Rs\.?|CAD|C\$|AUD|A\$|NZD|NZ\$|USD|\$|EUR|€|GBP|£|JPY|¥|"
        r"kr\.?|zł|ft|kč|r\$|pts|fr\.?|¤)"
    )
    currency_match = re.search(token_pattern, clean_text, flags=re.IGNORECASE)

    raw_token = currency_match.group(0) if currency_match else None

    if raw_token:
        upper_token = raw_token.upper().strip()
        if upper_token in KNOWN_CURRENCIES:
            detected_currency = KNOWN_CURRENCIES[upper_token]
            currency_status = EvidenceStatus.FOUND
        elif upper_token in AMBIGUOUS_CURRENCIES:
            # Preserve raw notation; do NOT guess specific ISO code
            detected_currency = raw_token.strip()
            currency_status = EvidenceStatus.UNVERIFIED
        else:
            detected_currency = raw_token.strip()
            currency_status = EvidenceStatus.UNVERIFIED

    # 2. Page-level currency resolution if card token is missing or generic
    if page_currency and page_currency.strip():
        norm_page_curr = page_currency.strip().upper()
        if detected_currency is None or currency_status == EvidenceStatus.UNVERIFIED:
            detected_currency = norm_page_curr
            currency_status = EvidenceStatus.FOUND
        elif detected_currency == "USD" and norm_page_curr in ("CAD", "AUD", "NZD", "USD"):
            # When page explicitly specifies CAD/AUD/NZD, disambiguate generic '$'
            detected_currency = norm_page_curr
            currency_status = EvidenceStatus.FOUND

    # 3. Extract numeric price value
    # Filter out percentages (e.g. '20%') or quantities (e.g. '2 items')
    # Prioritize numbers adjacent to currency symbols
    adjacent_pattern = (
        r"(?:₹|INR|Rs\.?|CAD|C\$|AUD|A\$|NZD|NZ\$|USD|\$|EUR|€|GBP|£|JPY|¥|"
        r"kr\.?|zł|ft|kč|r\$|pts|fr\.?|¤)\s*([0-9][0-9\.,\s]*)"
    )
    rev_adjacent_pattern = (
        r"([0-9][0-9\.,\s]*)\s*(?:₹|INR|Rs\.?|CAD|C\$|AUD|A\$|NZD|NZ\$|USD|\$|"
        r"EUR|€|GBP|£|JPY|¥|kr\.?|zł|ft|kč|r\$|pts|fr\.?|¤)"
    )

    numeric_val: float | None = None

    adj_match = re.search(adjacent_pattern, clean_text, flags=re.IGNORECASE)
    if adj_match:
        numeric_val = parse_clean_float(adj_match.group(1))

    if numeric_val is None:
        rev_match = re.search(rev_adjacent_pattern, clean_text, flags=re.IGNORECASE)
        if rev_match:
            numeric_val = parse_clean_float(rev_match.group(1))

    # Fallback: scan for any clean price number not followed by '%'
    if numeric_val is None:
        number_tokens = re.finditer(r"\b([0-9]+(?:[\.,][0-9]+)*)\b(?!\s*%)", clean_text)
        for m in number_tokens:
            cand = parse_clean_float(m.group(1))
            if cand is not None:
                numeric_val = cand
                break

    return numeric_val, detected_currency, currency_status


@dataclass
class CrawlRecordInput:
    """Convenience D2-compatible crawl record input structure."""

    source_url: str
    canonical_url: str = ""
    page_type: str = "product"
    rendered_html: str = ""
    visible_text: str = ""
    access_state: str = "Accessible"
    fetch_timestamp: str = ""


class DOMProductExtractor:
    """Extracts product information deterministically from HTML product card DOM elements."""

    def __init__(self, confidence: float = 0.8) -> None:
        self.confidence = confidence

    def extract_from_html(
        self,
        html: str,
        source_url: str = "",
        observed_at: datetime | None = None,
        page_type: str | None = None,
    ) -> list[ExtractedProduct]:
        """Extract product cards from rendered HTML string."""
        if not html or not html.strip():
            return []

        if observed_at is None:
            observed_at = datetime.now(timezone.utc)

        soup = BeautifulSoup(html, "html.parser")

        # 1. Inspect page-level currency clues (meta tags or data attributes)
        page_currency = self._extract_page_currency(soup)

        # 2. Identify product card containers
        cards = self._find_product_card_elements(soup)

        # 3. Extract products from each identified card
        products: list[ExtractedProduct] = []
        for card in cards:
            product = self._extract_card_product(
                card,
                source_url=source_url,
                observed_at=observed_at,
                page_currency=page_currency,
            )
            if product:
                products.append(product)

        # 4. Fallback for single product pages if no cards found
        if not products and (page_type in ("product", "product_detail", None)):
            single_product = self._extract_single_page_product(
                soup,
                source_url=source_url,
                observed_at=observed_at,
                page_currency=page_currency,
                page_type=page_type,
            )
            if single_product:
                products.append(single_product)

        return self._deduplicate_products(products)

    def _deduplicate_products(
        self,
        products: list[ExtractedProduct],
    ) -> list[ExtractedProduct]:
        """Deduplicate products with identical URL/title identity while preserving order."""
        seen_keys: set[tuple[str, ...]] = set()
        deduped: list[ExtractedProduct] = []
        for p in products:
            key = self._get_product_identity_key(p)
            if key is None or key not in seen_keys:
                if key is not None:
                    seen_keys.add(key)
                deduped.append(p)
        return deduped

    def _get_product_identity_key(self, p: ExtractedProduct) -> tuple[str, ...] | None:
        url = str(p.get("product.url") or "").strip()
        title = str(p.get("product.title") or "").strip()
        price = str(p.get("product.price") or "").strip()
        if url and title:
            return ("url_title", url, title)
        if url:
            return ("url", url)
        if title and price:
            return ("title_price", title, price)
        if title:
            return ("title", title)
        return None

    def extract_from_crawl_record(
        self,
        record: Any,
        allowed_page_types: Sequence[str | Enum] | None = None,
    ) -> list[ExtractedProduct]:
        """Extract products from a D2 CrawlRecord object, dict, or compatible duck-type.

        Skips extraction if CrawlRecord access_state is blocked or inaccessible.
        Filters by allowed_page_types when specified.
        """
        if record is None:
            return []

        # 1. Check access_state
        access_state = getattr(record, "access_state", None)
        if access_state is None and isinstance(record, dict):
            access_state = record.get("access_state")

        access_state_str = (
            access_state.value
            if isinstance(access_state, Enum)
            else str(access_state or "Accessible")
        )

        # Inaccessible / Blocked / Unavailable records are NOT processed
        if access_state_str.strip().lower() != "accessible":
            return []

        # 2. Check page_type routing
        page_type = getattr(record, "page_type", None)
        if page_type is None and isinstance(record, dict):
            page_type = record.get("page_type")

        page_type_str = (
            page_type.value if isinstance(page_type, Enum) else str(page_type or "")
        )

        if allowed_page_types is not None:
            allowed_set = {
                t.value.lower() if isinstance(t, Enum) else str(t).lower()
                for t in allowed_page_types
            }
            if page_type_str.lower() not in allowed_set:
                return []

        # 3. Extract source URL and HTML
        source_url = (
            getattr(record, "source_url", "")
            or getattr(record, "canonical_url", "")
        )
        if not source_url and isinstance(record, dict):
            source_url = record.get("source_url") or record.get("canonical_url", "")

        html = getattr(record, "rendered_html", "")
        if not html and isinstance(record, dict):
            html = record.get("rendered_html", "")

        # 4. Extract timestamp if present
        fetch_ts = getattr(record, "fetch_timestamp", None)
        if fetch_ts is None and isinstance(record, dict):
            fetch_ts = record.get("fetch_timestamp")

        observed_at: datetime | None = None
        if isinstance(fetch_ts, str) and fetch_ts:
            try:
                observed_at = datetime.fromisoformat(fetch_ts.replace("Z", "+00:00"))
            except ValueError:
                observed_at = None

        return self.extract_from_html(
            html=html,
            source_url=source_url,
            observed_at=observed_at,
            page_type=page_type_str,
        )

    def _extract_page_currency(self, soup: BeautifulSoup) -> str | None:
        """Inspect page-level meta tags or root attributes for confirmed currency."""
        # Check <meta itemprop="priceCurrency" content="...">
        meta_curr = soup.find(
            "meta",
            attrs={"itemprop": lambda v: v and "pricecurrency" in v.lower()},
        )
        if meta_curr and meta_curr.get("content"):
            return str(meta_curr["content"]).strip().upper()

        # Check <meta property="og:price:currency" content="...">
        og_curr = soup.find(
            "meta",
            property=lambda v: v and "price:currency" in v.lower(),
        )
        if og_curr and og_curr.get("content"):
            return str(og_curr["content"]).strip().upper()

        # Check data-currency attributes on html or body
        for tag_name in ("html", "body"):
            tag = soup.find(tag_name)
            if tag and tag.get("data-currency"):
                return str(tag["data-currency"]).strip().upper()

        return None

    def _find_product_card_elements(self, soup: BeautifulSoup) -> list[Tag]:
        """Find candidate product card tags, deduplicating nested parents."""
        candidates: list[Tag] = []

        # 1. Match against known card selectors
        for sel in PRODUCT_CARD_SELECTORS:
            try:
                matches = soup.select(sel)
                candidates.extend(matches)
            except Exception:
                continue

        # 2. Generic fallback: repeated items/cards containing a link AND a price
        if not candidates:
            generic_selectors = (
                ".card",
                ".item",
                ".grid-item",
                ".col-item",
                "li",
                "article",
            )
            for sel in generic_selectors:
                try:
                    elements = soup.select(sel)
                    for el in elements:
                        if self._is_potential_card(el):
                            candidates.append(el)
                except Exception:
                    continue

        # 3. Deduplicate and remove nested containers (keep outermost cards)
        seen_tags: set[int] = set()
        unique_candidates: list[Tag] = []
        for c in candidates:
            tag_id = id(c)
            if tag_id not in seen_tags:
                seen_tags.add(tag_id)
                unique_candidates.append(c)

        outermost_cards: list[Tag] = []
        for card in unique_candidates:
            # If any other candidate is an ancestor of card, skip it
            is_nested = any(
                other is not card and other in card.parents
                for other in unique_candidates
            )
            if not is_nested and self._card_has_product_evidence(card):
                outermost_cards.append(card)

        return outermost_cards

    def _is_potential_card(self, el: Tag) -> bool:
        """Check if an element contains at least a link and a price-like element or text."""
        has_link = bool(el.find("a", href=True))
        has_price = bool(
            el.find(attrs={"class": lambda c: c and any(p in c.lower() for p in ("price", "amount", "money"))})
            or re.search(r"[₹\$€£]|INR|USD|EUR|GBP|\b\d+(?:[\.,]\d+)?\b", el.get_text())
        )
        return has_link and has_price

    def _card_has_product_evidence(self, card: Tag) -> bool:
        """Verify element contains at least title, URL, or price."""
        has_link = bool(card.find("a", href=True))
        has_title = bool(self._extract_card_title(card))
        has_price = bool(self._extract_card_price_text(card))
        return has_link or has_title or has_price

    def _clean_title_element_text(self, el: Tag) -> str:
        """Extract title text from element, stripping any embedded price child tags or trailing price."""
        price_children = el.select(", ".join(PRICE_SELECTORS))
        if price_children:
            temp_soup = BeautifulSoup(str(el), "html.parser")
            root_tag = temp_soup.find()
            if root_tag and isinstance(root_tag, Tag):
                for p_child in root_tag.select(", ".join(PRICE_SELECTORS)):
                    p_child.decompose()
                raw_text = root_tag.get_text()
            else:
                raw_text = el.get_text()
        else:
            raw_text = el.get_text()

        normalized = normalize_whitespace(raw_text)
        # Strip trailing currency price regex if unclosed HTML leaked price into title text
        cleaned = re.sub(
            r"(?:₹|INR|Rs\.?|\$|USD|€|EUR|£|GBP|¥|JPY|kr\.?|¤)\s*[0-9][0-9\.,\s]*$",
            "",
            normalized,
            flags=re.IGNORECASE,
        ).strip()
        return cleaned if cleaned else normalized

    def _extract_card_title(self, card: Tag) -> str | None:
        """Extract and clean title from product card."""
        # 1. Check title selectors
        for sel in TITLE_SELECTORS:
            try:
                el = card.select_one(sel)
                if el:
                    text = self._clean_title_element_text(el)
                    if text and text.lower() not in IGNORED_TITLE_PHRASES:
                        return text
            except Exception:
                continue

        # 2. Check <a> tags with descriptive text
        for a_tag in card.find_all("a"):
            text = self._clean_title_element_text(a_tag)
            if text and text.lower() not in IGNORED_TITLE_PHRASES:
                # Disregard pure price or numeric text
                if not re.match(r"^[₹\$€£0-9\.,\s]+$", text):
                    return text

        # 3. Check image alt attribute
        img = card.find("img", alt=True)
        if img and img.get("alt"):
            alt_text = normalize_whitespace(img["alt"])
            if alt_text and alt_text.lower() not in IGNORED_TITLE_PHRASES:
                return alt_text

        return None

    def _extract_card_url(self, card: Tag, source_url: str) -> str | None:
        """Extract product URL from card and resolve relative URLs against source_url."""
        # 1. Prefer link wrapping the title
        title_el = None
        for sel in TITLE_SELECTORS:
            try:
                title_el = card.select_one(sel)
                if title_el:
                    break
            except Exception:
                continue

        if title_el:
            if title_el.name == "a" and title_el.get("href"):
                return self._resolve_url(title_el["href"], source_url)
            parent_a = title_el.find_parent("a", href=True)
            if parent_a and parent_a.get("href"):
                return self._resolve_url(parent_a["href"], source_url)
            child_a = title_el.find("a", href=True)
            if child_a and child_a.get("href"):
                return self._resolve_url(child_a["href"], source_url)

        # 2. Scan all <a> tags in card, prioritizing product links
        product_link_candidates: list[str] = []
        fallback_link_candidates: list[str] = []

        for a in card.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue
            lower_href = href.lower()
            if any(p in lower_href for p in ("/product/", "/products/", "/item/", "/items/", "/p/")):
                product_link_candidates.append(href)
            elif not any(ign in lower_href for ign in ("cart", "wishlist", "checkout", "account")):
                fallback_link_candidates.append(href)

        if product_link_candidates:
            return self._resolve_url(product_link_candidates[0], source_url)
        if fallback_link_candidates:
            return self._resolve_url(fallback_link_candidates[0], source_url)

        return None

    def _resolve_url(self, href: str, source_url: str) -> str | None:
        """Normalize URL and resolve against source_url if relative."""
        cleaned = href.strip()
        if not cleaned or cleaned.startswith(("#", "javascript:")):
            return None
        if source_url:
            return urljoin(source_url, cleaned)
        return cleaned

    def _extract_card_price_text(self, card: Tag) -> str | None:
        """Find the main visible price text inside card, avoiding was/strikethrough elements."""
        # 1. Check price selectors, skipping was/old/strikethrough elements
        for sel in PRICE_SELECTORS:
            try:
                matches = card.select(sel)
                for el in matches:
                    el_classes = (
                        " ".join(el.get("class", []))
                        if isinstance(el.get("class"), list)
                        else str(el.get("class", ""))
                    )
                    if any(w in el_classes.lower() for w in ("was", "old", "regular", "compare", "original")):
                        continue
                    if el.find_parent(["del", "s", "strike"]):
                        continue
                    text = normalize_whitespace(el.get_text())
                    if text and re.search(r"\d", text):
                        return text
            except Exception:
                continue

        # 2. Fallback: search text of card for currency/price regex
        text = normalize_whitespace(card.get_text())
        price_match = re.search(
            r"(?:₹|INR|Rs\.?|\$|USD|€|EUR|£|GBP|¥|JPY|kr\.?|¤)\s*[0-9][0-9\.,\s]*",
            text,
            flags=re.IGNORECASE,
        )
        if price_match:
            return price_match.group(0)

        return None

    def _extract_card_product(
        self,
        card: Tag,
        source_url: str,
        observed_at: datetime,
        page_currency: str | None = None,
    ) -> ExtractedProduct | None:
        """Extract and build ExtractedProduct from a single card container."""
        title = self._extract_card_title(card)
        url = self._extract_card_url(card, source_url)

        # Inspect prices: check for sale vs original/strikethrough prices
        orig_price: float | None = None
        disc_price: float | None = None
        current_price: float | None = None
        currency_val: str | None = None
        currency_status = EvidenceStatus.NOT_FOUND

        # Check for strikethrough/old/was price elements
        del_el = card.find(["del", "s", "strike"]) or card.select_one(
            '[class*="old"], [class*="regular-price"], [class*="original-price"], [class*="compare"], [class*="was"]'
        )
        if del_el:
            del_text = normalize_whitespace(del_el.get_text())
            orig_p, orig_c, _ = normalize_price_and_currency(del_text, page_currency)
            orig_price = orig_p

        # Check for sale/current price elements
        sale_el = card.select_one(
            '[class*="sale-price"], [class*="current-price"], [class*="special-price"], [class*="now"]'
        )
        if sale_el:
            sale_text = normalize_whitespace(sale_el.get_text())
            cur_p, cur_c, cur_stat = normalize_price_and_currency(sale_text, page_currency)
            current_price = cur_p
            currency_val = cur_c
            currency_status = cur_stat

        # Fallback generic price extraction
        if current_price is None:
            price_text = self._extract_card_price_text(card)
            cur_p, cur_c, cur_stat = normalize_price_and_currency(price_text, page_currency)
            current_price = cur_p
            currency_val = cur_c
            currency_status = cur_stat

        if orig_price is not None and current_price is not None:
            if orig_price > current_price:
                disc_price = current_price

        # Do not emit if neither title, url, nor price is present
        if not (title or url or current_price is not None):
            return None

        # Build records map strictly adhering to the EvidenceRecord contract
        records: dict[str, EvidenceRecord] = {}

        values_map: dict[str, Any] = {
            "product.title": title,
            "product.url": url,
            "product.price": current_price,
            "product.currency": currency_val,
            "product.description": None,
            "product.availability": None,
            "product.original_price": orig_price,
            "product.discount_price": disc_price,
        }

        for field_name in SUPPORTED_PRODUCT_FIELDS:
            val = values_map[field_name]
            if field_name == "product.currency":
                status = currency_status
            else:
                status = EvidenceStatus.FOUND if val is not None else EvidenceStatus.NOT_FOUND

            records[field_name] = EvidenceRecord(
                field=field_name,
                value=val,
                status=status,
                source_url=source_url,
                observed_at=observed_at,
                method=EvidenceMethod.DOM,
                confidence=self.confidence,
            )

        return ExtractedProduct(records=records)

    def _extract_single_page_product(
        self,
        soup: BeautifulSoup,
        source_url: str,
        observed_at: datetime,
        page_currency: str | None = None,
        page_type: str | None = None,
    ) -> ExtractedProduct | None:
        """Extract a single product from product detail page elements when no cards exist."""
        has_explicit_product_container = bool(
            soup.find(attrs={"class": lambda c: c and any(k in c.lower() for k in ("product-single", "product-detail", "product-main"))})
            or soup.find(attrs={"itemtype": lambda t: t and "schema.org/product" in t.lower()})
        )

        is_product_route = bool(
            (page_type and page_type.lower() in ("product", "product_detail"))
            or (source_url and any(p in source_url.lower() for p in ("/product/", "/products/", "/item/", "/items/", "/p/")))
        )

        # Find product container
        container = (
            soup.find(attrs={"class": lambda c: c and any(k in c.lower() for k in ("product-single", "product-detail", "product-main"))})
            or soup.find("main")
            or soup.find("body")
        )
        if not container or not isinstance(container, Tag):
            return None

        title_el = container.find("h1") or container.select_one('[class*="product-title"], [itemprop="name"]')
        title = normalize_whitespace(title_el.get_text()) if title_el else None

        price_text = self._extract_card_price_text(container)
        price, curr, curr_stat = normalize_price_and_currency(price_text, page_currency)

        # Conservative gating: must have a price, OR an explicit product container/route with a title
        if price is not None:
            pass
        elif title and (has_explicit_product_container or is_product_route):
            pass
        else:
            return None

        records: dict[str, EvidenceRecord] = {}
        values_map: dict[str, Any] = {
            "product.title": title,
            "product.url": source_url or None,
            "product.price": price,
            "product.currency": curr,
            "product.description": None,
            "product.availability": None,
            "product.original_price": None,
            "product.discount_price": None,
        }

        for field_name in SUPPORTED_PRODUCT_FIELDS:
            val = values_map[field_name]
            if field_name == "product.currency":
                status = curr_stat
            else:
                status = EvidenceStatus.FOUND if val is not None else EvidenceStatus.NOT_FOUND

            records[field_name] = EvidenceRecord(
                field=field_name,
                value=val,
                status=status,
                source_url=source_url,
                observed_at=observed_at,
                method=EvidenceMethod.DOM,
                confidence=self.confidence,
            )

        return ExtractedProduct(records=records)


def extract_products_dom(
    html: str,
    source_url: str = "",
    observed_at: datetime | None = None,
    confidence: float = 0.8,
) -> list[ExtractedProduct]:
    """Convenience helper function to extract products from DOM in HTML."""
    extractor = DOMProductExtractor(confidence=confidence)
    return extractor.extract_from_html(
        html=html,
        source_url=source_url,
        observed_at=observed_at,
    )
