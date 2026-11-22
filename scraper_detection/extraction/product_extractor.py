"""JSON-LD Product Extractor (Developer 3 - Scraping & Detection).

Deterministic extraction of product metadata from schema.org JSON-LD scripts.
Adheres strictly to the EvidenceRecord contract and never fabricates missing fields.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper_detection.schemas.evidence import (
    EvidenceMethod,
    EvidenceRecord,
    EvidenceStatus,
)

# Canonical product fields supported by the D3 field specification
SUPPORTED_PRODUCT_FIELDS = (
    "product.title",
    "product.url",
    "product.price",
    "product.currency",
    "product.description",
    "product.availability",
    "product.original_price",
    "product.discount_price",
)


@dataclass
class ExtractedProduct:
    """Represents a product extracted from JSON-LD containing field-level EvidenceRecords."""

    records: dict[str, EvidenceRecord] = field(default_factory=dict)

    def get(self, field_name: str, default: Any = None) -> Any:
        record = self.records.get(field_name)
        if record and record.status == EvidenceStatus.FOUND:
            return record.value
        return default

    def get_record(self, field_name: str) -> EvidenceRecord | None:
        return self.records.get(field_name)

    def is_found(self, field_name: str) -> bool:
        record = self.records.get(field_name)
        return bool(record and record.status == EvidenceStatus.FOUND)

    @property
    def found_records(self) -> dict[str, EvidenceRecord]:
        return {
            k: v
            for k, v in self.records.items()
            if v.status == EvidenceStatus.FOUND
        }

    def to_evidence_list(self) -> list[EvidenceRecord]:
        return list(self.records.values())

    def __getitem__(self, field_name: str) -> EvidenceRecord:
        return self.records[field_name]

    def __contains__(self, field_name: str) -> bool:
        return field_name in self.records


class JSONLDProductExtractor:
    """Extracts product information deterministically from JSON-LD script elements."""

    def __init__(self, confidence: float = 1.0) -> None:
        self.confidence = confidence

    def extract_from_html(
        self,
        html: str,
        source_url: str = "",
        observed_at: datetime | None = None,
    ) -> list[ExtractedProduct]:
        """Parse HTML, locate all application/ld+json scripts, and extract products."""
        if not html or not html.strip():
            return []

        if observed_at is None:
            observed_at = datetime.now(timezone.utc)

        soup = BeautifulSoup(html, "html.parser")
        script_tags = soup.find_all(
            "script",
            type=lambda t: t and "application/ld+json" in t.lower(),
        )

        extracted_products: list[ExtractedProduct] = []

        for script in script_tags:
            content = script.string or script.get_text()
            if not content or not content.strip():
                continue

            try:
                parsed_json = json.loads(content)
            except (json.JSONDecodeError, TypeError, ValueError):
                # Malformed JSON-LD is ignored safely per Day 2 requirement 3
                continue

            raw_entities = self._collect_entities(parsed_json)
            for entity in raw_entities:
                for product_dict in self._unpack_product_candidates(entity):
                    product = self._build_extracted_product(
                        product_dict,
                        source_url=source_url,
                        observed_at=observed_at,
                    )
                    if product:
                        extracted_products.append(product)

        return self._deduplicate_products(extracted_products)

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

    def _collect_entities(self, data: Any) -> list[dict[str, Any]]:
        """Flatten objects, lists, and @graph hierarchies into a list of entity dictionaries."""
        entities: list[dict[str, Any]] = []

        if isinstance(data, list):
            for item in data:
                entities.extend(self._collect_entities(item))
        elif isinstance(data, dict):
            # Unpack @graph if present
            if "@graph" in data:
                graph = data["@graph"]
                if isinstance(graph, (list, dict)):
                    entities.extend(self._collect_entities(graph))
            entities.append(data)

        return entities

    def _unpack_product_candidates(
        self,
        entity: dict[str, Any],
    ) -> Iterator[dict[str, Any]]:
        """Detect supported schema types (Product, ProductGroup, ItemList, Offer) and yield product dicts."""
        if not isinstance(entity, dict):
            return

        types = self._normalize_types(entity.get("@type"))

        # 1. ProductGroup: variants inherit parent metadata (e.g. name, description, offers)
        if "productgroup" in types:
            variants = entity.get("hasVariant")
            if variants:
                variant_list = variants if isinstance(variants, list) else [variants]
                for v in variant_list:
                    if isinstance(v, dict):
                        merged = self._merge_parent_context(parent=entity, child=v)
                        yield merged
                return
            # If no hasVariant, treat ProductGroup itself as a product-level entity
            yield entity
            return

        # 2. ItemList: contains items or list elements representing products
        if "itemlist" in types:
            elements = entity.get("itemListElement")
            if elements:
                element_list = elements if isinstance(elements, list) else [elements]
                for elem in element_list:
                    if isinstance(elem, dict):
                        inner_item = elem.get("item")
                        if isinstance(inner_item, dict):
                            yield from self._unpack_product_candidates(inner_item)
                        elif self._is_product_like(elem):
                            yield elem
            return

        # 3. Direct Product
        if "product" in types:
            yield entity
            return

        # 4. Standalone Offer with an itemOffered Product or named product offer
        if "offer" in types or "aggregateoffer" in types:
            item_offered = entity.get("itemOffered")
            if isinstance(item_offered, dict) and self._is_product_like(item_offered):
                # Merge the offer details into the itemOffered
                merged = dict(item_offered)
                merged.setdefault("offers", entity)
                yield merged
            elif entity.get("name") or entity.get("title"):
                # Standalone offer representing a purchasable named product/service
                yield entity

    def _is_product_like(self, entity: dict[str, Any]) -> bool:
        """Check if dictionary has Product or ProductGroup schema type."""
        types = self._normalize_types(entity.get("@type"))
        return bool({"product", "productgroup"}.intersection(types))

    def _normalize_types(self, raw_type: Any) -> set[str]:
        """Strip schema.org prefixes and return normalized lowercase types."""
        if not raw_type:
            return set()
        type_list = raw_type if isinstance(raw_type, list) else [raw_type]
        normalized = set()
        for t in type_list:
            if isinstance(t, str):
                cleaned = t.strip().lower()
                for prefix in ("https://schema.org/", "http://schema.org/"):
                    if cleaned.startswith(prefix):
                        cleaned = cleaned[len(prefix):]
                normalized.add(cleaned)
        return normalized

    def _merge_parent_context(
        self,
        parent: dict[str, Any],
        child: dict[str, Any],
    ) -> dict[str, Any]:
        """Inherit parent metadata (name, description, url, offers) for a variant if omitted in child."""
        merged = dict(child)
        for key in ("name", "title", "description", "url", "offers"):
            if key not in merged and key in parent:
                merged[key] = parent[key]
        return merged

    def _build_extracted_product(
        self,
        data: dict[str, Any],
        source_url: str,
        observed_at: datetime,
    ) -> ExtractedProduct | None:
        """Build an ExtractedProduct with EvidenceRecord instances for all supported fields."""
        # Extract raw field values
        title = self._extract_string(data, ("name", "title", "headline"))
        description = self._extract_string(data, ("description",))
        url = self._extract_url(data, source_url)

        # Offer details: price, currency, availability, discount, original price
        offer_info = self._extract_offer_details(data.get("offers"))

        # In case url is in offers and not on top-level
        if not url and offer_info.get("url"):
            url = offer_info["url"]

        # Only proceed if there is at least some minimal product evidence (title, url, or price)
        if not (title or url or offer_info.get("price") is not None):
            return None

        # Build records map for all supported fields
        records: dict[str, EvidenceRecord] = {}

        values_map: dict[str, Any] = {
            "product.title": title,
            "product.url": url,
            "product.price": offer_info.get("price"),
            "product.currency": offer_info.get("currency"),
            "product.description": description,
            "product.availability": offer_info.get("availability"),
            "product.original_price": offer_info.get("original_price"),
            "product.discount_price": offer_info.get("discount_price"),
        }

        for field_name in SUPPORTED_PRODUCT_FIELDS:
            val = values_map[field_name]
            if val is not None:
                status = EvidenceStatus.FOUND
            else:
                status = EvidenceStatus.NOT_FOUND

            records[field_name] = EvidenceRecord(
                field=field_name,
                value=val,
                status=status,
                source_url=source_url,
                observed_at=observed_at,
                method=EvidenceMethod.JSON_LD,
                confidence=self.confidence,
            )

        return ExtractedProduct(records=records)

    def _extract_string(
        self,
        data: dict[str, Any],
        candidate_keys: tuple[str, ...],
    ) -> str | None:
        """Extract and clean string value from one of candidate keys."""
        for key in candidate_keys:
            val = data.get(key)
            if isinstance(val, dict) and "@value" in val:
                val = val["@value"]
            if isinstance(val, str):
                cleaned = val.strip()
                if cleaned:
                    return cleaned
        return None

    def _extract_url(self, data: dict[str, Any], source_url: str) -> str | None:
        """Extract and normalize URL, joining with source_url if relative."""
        raw_url = data.get("url") or data.get("@id")
        if isinstance(raw_url, dict) and "@id" in raw_url:
            raw_url = raw_url["@id"]
        if isinstance(raw_url, str):
            cleaned = raw_url.strip()
            if cleaned and not cleaned.startswith(("_:", "#")):
                if source_url and not cleaned.startswith(("http://", "https://")):
                    return urljoin(source_url, cleaned)
                return cleaned
        return None

    def _extract_offer_details(self, offers: Any) -> dict[str, Any]:
        """Extract price, currency, availability, and discount/original prices from Offer(s)."""
        result: dict[str, Any] = {
            "price": None,
            "currency": None,
            "availability": None,
            "original_price": None,
            "discount_price": None,
            "url": None,
        }

        if not offers:
            return result

        offer_list = offers if isinstance(offers, list) else [offers]

        for offer in offer_list:
            if not isinstance(offer, dict):
                continue

            # Price extraction (supports 'price', 'lowPrice')
            raw_price = offer.get("price")
            if raw_price is None:
                raw_price = offer.get("lowPrice")
            parsed_price = self._parse_numeric(raw_price)
            if parsed_price is not None and result["price"] is None:
                result["price"] = parsed_price

            # Currency extraction (supports 'priceCurrency')
            raw_currency = offer.get("priceCurrency")
            if isinstance(raw_currency, str) and raw_currency.strip():
                clean_curr = raw_currency.strip().upper()
                if result["currency"] is None:
                    result["currency"] = clean_curr

            # Availability extraction
            raw_avail = offer.get("availability")
            if isinstance(raw_avail, str) and raw_avail.strip():
                if result["availability"] is None:
                    result["availability"] = raw_avail.strip()

            # URL from offer if present
            raw_url = offer.get("url")
            if isinstance(raw_url, str) and raw_url.strip() and result["url"] is None:
                result["url"] = raw_url.strip()

            # Original vs Discount Price inspection
            # 1. Check priceSpecification array
            price_spec = offer.get("priceSpecification")
            if price_spec:
                specs = price_spec if isinstance(price_spec, list) else [price_spec]
                for spec in specs:
                    if not isinstance(spec, dict):
                        continue
                    spec_type = str(spec.get("priceType", "")).lower()
                    spec_price = self._parse_numeric(spec.get("price"))
                    if spec_price is not None:
                        if any(k in spec_type for k in ("list", "original", "regular", "strikethrough")):
                            if result["original_price"] is None:
                                result["original_price"] = spec_price
                        elif any(k in spec_type for k in ("sale", "discount")):
                            if result["discount_price"] is None:
                                result["discount_price"] = spec_price

            # 2. Check explicit highPrice / compareAtPrice / originalPrice
            raw_orig = (
                offer.get("originalPrice")
                or offer.get("compareAtPrice")
                or offer.get("listPrice")
                or offer.get("regularPrice")
            )
            parsed_orig = self._parse_numeric(raw_orig)
            if parsed_orig is not None and result["original_price"] is None:
                result["original_price"] = parsed_orig

            raw_disc = offer.get("discountPrice") or offer.get("salePrice")
            parsed_disc = self._parse_numeric(raw_disc)
            if parsed_disc is not None and result["discount_price"] is None:
                result["discount_price"] = parsed_disc

            # 3. AggregateOffer highPrice when higher than lowPrice
            high_price = self._parse_numeric(offer.get("highPrice"))
            if high_price is not None and parsed_price is not None:
                if high_price > parsed_price and result["original_price"] is None:
                    # In an aggregate offer context, highPrice may be the regular or ceiling price
                    pass

        return result

    def _parse_numeric(self, val: Any) -> float | None:
        """Parse float/int/string to float deterministically without guessing."""
        if val is None or val == "":
            return None
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, str):
            cleaned = val.strip().replace(",", "")
            # Extract standard floating number sequence
            match = re.search(r"\d+(?:\.\d+)?", cleaned)
            if match:
                try:
                    return float(match.group(0))
                except (ValueError, OverflowError):
                    return None
        return None


def extract_products_json_ld(
    html: str,
    source_url: str = "",
    observed_at: datetime | None = None,
) -> list[ExtractedProduct]:
    """Convenience helper function to extract products from JSON-LD in HTML."""
    extractor = JSONLDProductExtractor()
    return extractor.extract_from_html(html, source_url=source_url, observed_at=observed_at)
