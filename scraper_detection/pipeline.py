"""D3 Pipeline Facade (Developer 3 - Scraping & Detection).

Orchestrates deterministic extraction and technology detection across crawled pages:
- JSON-LD product extraction
- DOM product extraction (fallback)
- Store profile details (name, about text)
- Business contact & social links
- E-commerce platform fingerprint rules (Shopify, WooCommerce, Magento)

Consumes D2 CrawlBundle / CrawlRecord objects without importing Playwright or
browser automation internals. Emits canonical EvidenceRecord collections for
downstream D4 validation/scoring and D1 persistence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Sequence

from scraper_detection.detection.platform_detector import (
    PlatformDetectionResult,
    PlatformDetector,
)
from scraper_detection.extraction.contact_social_extractor import (
    ContactSocialExtractor,
    ExtractedContactSocial,
)
from scraper_detection.extraction.dom_product_extractor import (
    DOMProductExtractor,
)
from scraper_detection.extraction.product_extractor import (
    ExtractedProduct,
    JSONLDProductExtractor,
)
from scraper_detection.extraction.store_extractor import (
    ExtractedStoreDetails,
    StoreExtractor,
)
from scraper_detection.schemas.evidence import (
    EvidenceMethod,
    EvidenceRecord,
    EvidenceStatus,
)


@dataclass
class StoreExtractionResult:
    """Consolidated extraction and detection results for a store crawl.

    Provides both granular typed results (platform, store, contact_social, products)
    and a unified list of canonical EvidenceRecord objects for D4/D1 consumption.
    """

    base_url: str
    records_analyzed: int
    platform: PlatformDetectionResult
    store: ExtractedStoreDetails
    contact_social: ExtractedContactSocial
    products: list[ExtractedProduct]
    evidence_records: list[EvidenceRecord] = field(default_factory=list)

    def get_evidence(self, field_name: str) -> EvidenceRecord | None:
        """Retrieve the primary EvidenceRecord for a specific field name."""
        for rec in self.evidence_records:
            if rec.field == field_name:
                return rec
        return None

    def get_evidence_list(self, field_prefix: str) -> list[EvidenceRecord]:
        """Retrieve all EvidenceRecords matching a prefix (e.g. 'product.', 'social.')."""
        return [r for r in self.evidence_records if r.field.startswith(field_prefix)]

    def to_dict(self) -> dict[str, Any]:
        """Serialize extraction results to a JSON-safe dictionary."""
        return {
            "base_url": self.base_url,
            "records_analyzed": self.records_analyzed,
            "detected_platform": self.platform.platform,
            "platform_confidence": (
                self.platform.evidence.confidence if self.platform.evidence else 0.0
            ),
            "store_name": (
                self.store.records["store.name"].value
                if "store.name" in self.store.records
                else None
            ),
            "store_about_text": (
                self.store.records["store.about_text"].value
                if "store.about_text" in self.store.records
                else None
            ),
            "contact_email": (
                self.contact_social.records["contact.email"].value
                if "contact.email" in self.contact_social.records
                else None
            ),
            "contact_phone": (
                self.contact_social.records["contact.phone"].value
                if "contact.phone" in self.contact_social.records
                else None
            ),
            "product_count": len(self.products),
            "total_evidence_records": len(self.evidence_records),
        }


class D3ExtractionPipeline:
    """Orchestrates all Developer 3 extractors over crawled page records."""

    def __init__(self) -> None:
        self.platform_detector = PlatformDetector()
        self.store_extractor = StoreExtractor()
        self.contact_social_extractor = ContactSocialExtractor()
        self.json_ld_extractor = JSONLDProductExtractor()
        self.dom_product_extractor = DOMProductExtractor()

    def process_bundle(self, crawl_bundle: Any) -> StoreExtractionResult:
        """Process a D2 CrawlBundle or record collection and return StoreExtractionResult.

        Accepts:
            - A D2 CrawlBundle object (with .base_url and .records)
            - A dict representing a CrawlBundle
            - A sequence of CrawlRecord objects
        """
        # 1. Unpack records and base_url
        records: list[Any] = []
        base_url = ""

        if hasattr(crawl_bundle, "records") and hasattr(crawl_bundle, "base_url"):
            records = list(crawl_bundle.records or [])
            base_url = str(crawl_bundle.base_url or "")
        elif isinstance(crawl_bundle, dict):
            records = list(crawl_bundle.get("records", []))
            base_url = str(crawl_bundle.get("base_url", ""))
        elif isinstance(crawl_bundle, (list, tuple)):
            records = list(crawl_bundle)
            if records:
                first = records[0]
                base_url = getattr(first, "source_url", "") or getattr(
                    first, "canonical_url", ""
                )
                if not base_url and isinstance(first, dict):
                    base_url = first.get("source_url") or first.get("canonical_url", "")

        # 2. Run Platform Detection across bundle
        platform_result = self.platform_detector.detect_from_crawl_bundle(crawl_bundle)

        # 3. Run Store Details Extraction across records
        store_result = self.store_extractor.extract_from_crawl_records(records)

        # 4. Run Contact & Social Extraction across records
        cs_result = self.contact_social_extractor.extract_from_crawl_records(records)

        # 5. Run Product Extraction (JSON-LD first, DOM fallback) across accessible records
        all_products = self._extract_products_from_records(records)

        # 6. Assemble canonical EvidenceRecord collection
        evidence_records: list[EvidenceRecord] = []

        # Platform evidence
        if platform_result.evidence:
            evidence_records.append(platform_result.evidence)

        # Store details evidence
        for rec in store_result.records.values():
            evidence_records.append(rec)

        # Contact & Social evidence
        for rec in cs_result.records.values():
            evidence_records.append(rec)

        # Product evidence (per extracted product)
        for prod in all_products:
            for rec in prod.records.values():
                evidence_records.append(rec)

        # Ensure every produced evidence record has a non-empty source_url
        if base_url:
            for ev in evidence_records:
                if not ev.source_url:
                    ev.source_url = base_url

        return StoreExtractionResult(
            base_url=base_url,
            records_analyzed=len(records),
            platform=platform_result,
            store=store_result,
            contact_social=cs_result,
            products=all_products,
            evidence_records=evidence_records,
        )

    def _extract_products_from_records(
        self,
        records: Sequence[Any],
    ) -> list[ExtractedProduct]:
        """Extract products from accessible records, prioritizing JSON-LD over DOM."""
        combined_products: list[ExtractedProduct] = []
        seen_identities: set[tuple[str, ...]] = set()

        for rec in records:
            # Check access state
            access_state = getattr(rec, "access_state", None)
            if access_state is None and isinstance(rec, dict):
                access_state = rec.get("access_state")

            access_state_str = (
                access_state.value
                if isinstance(access_state, Enum)
                else str(access_state or "Accessible")
            )
            if access_state_str.strip().lower() != "accessible":
                continue

            # Route by page type: skip dedicated about/contact pages for product extraction
            page_type = getattr(rec, "page_type", None)
            if page_type is None and isinstance(rec, dict):
                page_type = rec.get("page_type")
            page_type_str = (
                page_type.value
                if isinstance(page_type, Enum)
                else str(page_type or "")
            )
            if page_type_str.strip().lower() in ("about", "contact"):
                continue

            # Step A: Try JSON-LD extraction
            json_ld_prods = self.json_ld_extractor.extract_from_crawl_record(rec)

            # Step B: If JSON-LD found products, accept them
            if json_ld_prods:
                for p in json_ld_prods:
                    key = self._product_identity_key(p)
                    if key is None or key not in seen_identities:
                        if key is not None:
                            seen_identities.add(key)
                        combined_products.append(p)
            else:
                # Step C: Fall back to DOM product extraction
                dom_prods = self.dom_product_extractor.extract_from_crawl_record(rec)
                for p in dom_prods:
                    key = self._product_identity_key(p)
                    if key is None or key not in seen_identities:
                        if key is not None:
                            seen_identities.add(key)
                        combined_products.append(p)

        return combined_products

    def _product_identity_key(
        self,
        p: ExtractedProduct,
    ) -> tuple[str, ...] | None:
        """Derive identity key for deduplicating products across pages."""
        url_rec = p.records.get("product.url")
        url_val = (
            url_rec.value.strip().lower()
            if url_rec and isinstance(url_rec.value, str) and url_rec.value.strip()
            else None
        )
        if url_val:
            return ("url", url_val)

        title_rec = p.records.get("product.title")
        title_val = (
            title_rec.value.strip().lower()
            if title_rec and isinstance(title_rec.value, str) and title_rec.value.strip()
            else None
        )
        if title_val:
            return ("title", title_val)

        return None


def extract_store_data(crawl_bundle: Any) -> StoreExtractionResult:
    """Canonical D3 pipeline entry point.

    Accepts a D2 CrawlBundle, CrawlRecord list, or bundle dictionary, and
    runs the full deterministic extraction & platform detection suite.

    Returns:
        StoreExtractionResult containing typed sub-results and a flat
        list of canonical EvidenceRecord objects.
    """
    pipeline = D3ExtractionPipeline()
    return pipeline.process_bundle(crawl_bundle)
