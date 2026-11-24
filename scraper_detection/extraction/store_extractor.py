"""Store Details Extractor (Developer 3 - Scraping & Detection).

Deterministic extraction of public store details (business name, visible About/Contact text)
from HTML and D2 CrawlRecord / CrawlBundle models using BeautifulSoup4.
Strictly adheres to the EvidenceRecord contract and never invents or hallucinates facts.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Sequence

from bs4 import BeautifulSoup, Tag

from scraper_detection.schemas.evidence import (
    EvidenceMethod,
    EvidenceRecord,
    EvidenceStatus,
)

SUPPORTED_STORE_FIELDS: tuple[str, ...] = (
    "store.name",
    "store.about_text",
)

# Common generic title suffixes or prefixes to strip when extracting clean store name
GENERIC_TITLE_NOISE: tuple[str, ...] = (
    "official store",
    "official website",
    "official online store",
    "online store",
    "online shopping",
    "home page",
    "homepage",
    "welcome",
    "buy online",
    "shop online",
)


@dataclass
class ExtractedStoreDetails:
    """Represents extracted store metadata with field-level EvidenceRecord instances."""

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

    def to_evidence_list(self) -> list[EvidenceRecord]:
        return list(self.records.values())

    def __getitem__(self, field_name: str) -> EvidenceRecord:
        return self.records[field_name]

    def __contains__(self, field_name: str) -> bool:
        return field_name in self.records


class StoreExtractor:
    """Extracts public store name and About/Contact text deterministically using BeautifulSoup4."""

    def __init__(self, confidence: float = 0.85) -> None:
        self.confidence = confidence

    def extract_from_html(
        self,
        html: str,
        source_url: str = "",
        observed_at: datetime | None = None,
        page_type: str | None = None,
    ) -> ExtractedStoreDetails:
        """Extract store name and public About/Contact text from HTML string."""
        if observed_at is None:
            observed_at = datetime.now(timezone.utc)

        if not html or not html.strip():
            return self._build_empty_result(source_url, observed_at)

        soup = BeautifulSoup(html, "html.parser")

        # 1. Extract Store Name
        store_name, name_method, name_conf = self._extract_store_name(soup)

        # 2. Extract Public About / Contact Text
        about_text, about_method, about_conf = self._extract_about_text(soup, page_type=page_type)

        records: dict[str, EvidenceRecord] = {}

        # store.name
        if store_name:
            records["store.name"] = EvidenceRecord(
                field="store.name",
                value=store_name,
                status=EvidenceStatus.FOUND,
                source_url=source_url,
                observed_at=observed_at,
                method=name_method,
                confidence=name_conf,
            )
        else:
            records["store.name"] = EvidenceRecord(
                field="store.name",
                value=None,
                status=EvidenceStatus.NOT_OBSERVED,
                source_url=source_url,
                observed_at=observed_at,
                method=EvidenceMethod.DOM,
                confidence=self.confidence,
            )

        # store.about_text
        if about_text:
            records["store.about_text"] = EvidenceRecord(
                field="store.about_text",
                value=about_text,
                status=EvidenceStatus.FOUND,
                source_url=source_url,
                observed_at=observed_at,
                method=about_method,
                confidence=about_conf,
            )
        else:
            records["store.about_text"] = EvidenceRecord(
                field="store.about_text",
                value=None,
                status=EvidenceStatus.NOT_OBSERVED,
                source_url=source_url,
                observed_at=observed_at,
                method=EvidenceMethod.DOM,
                confidence=self.confidence,
            )

        return ExtractedStoreDetails(records=records)

    def extract_from_crawl_record(self, record: Any) -> ExtractedStoreDetails:
        """Extract store details from a D2 CrawlRecord object, dict, or duck-type."""
        if record is None:
            return self._build_empty_result("", datetime.now(timezone.utc))

        access_state = getattr(record, "access_state", None)
        if access_state is None and isinstance(record, dict):
            access_state = record.get("access_state")

        access_state_str = (
            access_state.value
            if isinstance(access_state, Enum)
            else str(access_state or "Accessible")
        )

        source_url = (
            getattr(record, "source_url", "")
            or getattr(record, "canonical_url", "")
        )
        if not source_url and isinstance(record, dict):
            source_url = record.get("source_url") or record.get("canonical_url", "")

        fetch_ts = getattr(record, "fetch_timestamp", None)
        if fetch_ts is None and isinstance(record, dict):
            fetch_ts = record.get("fetch_timestamp")

        observed_at: datetime | None = None
        if isinstance(fetch_ts, str) and fetch_ts:
            try:
                observed_at = datetime.fromisoformat(fetch_ts.replace("Z", "+00:00"))
            except ValueError:
                observed_at = None
        if observed_at is None:
            observed_at = datetime.now(timezone.utc)

        # Inaccessible/blocked records produce NOT_FOUND/BLOCKED
        if access_state_str.strip().lower() != "accessible":
            records: dict[str, EvidenceRecord] = {}
            for fld in SUPPORTED_STORE_FIELDS:
                records[fld] = EvidenceRecord(
                    field=fld,
                    value=None,
                    status=EvidenceStatus.BLOCKED,
                    source_url=source_url,
                    observed_at=observed_at,
                    method=EvidenceMethod.DOM,
                    confidence=self.confidence,
                )
            return ExtractedStoreDetails(records=records)

        html = getattr(record, "rendered_html", "")
        if not html and isinstance(record, dict):
            html = record.get("rendered_html", "")

        page_type = getattr(record, "page_type", None)
        if page_type is None and isinstance(record, dict):
            page_type = record.get("page_type")
        page_type_str = (
            page_type.value if isinstance(page_type, Enum) else str(page_type or "")
        )

        return self.extract_from_html(
            html=html,
            source_url=source_url,
            observed_at=observed_at,
            page_type=page_type_str,
        )

    def extract_from_crawl_records(
        self,
        records: Iterable[Any],
    ) -> ExtractedStoreDetails:
        """Aggregate store details across multiple crawled pages (e.g. CrawlBundle)."""
        combined_records: dict[str, EvidenceRecord] = {}
        now = datetime.now(timezone.utc)
        all_blocked = True
        record_count = 0
        first_source_url = ""

        # Initialize defaults
        for fld in SUPPORTED_STORE_FIELDS:
            combined_records[fld] = EvidenceRecord(
                field=fld,
                value=None,
                status=EvidenceStatus.NOT_OBSERVED,
                source_url="",
                observed_at=now,
                method=EvidenceMethod.DOM,
                confidence=self.confidence,
            )

        for rec in records:
            record_count += 1
            access_state = getattr(rec, "access_state", None)
            if access_state is None and isinstance(rec, dict):
                access_state = rec.get("access_state")
            access_state_str = (
                access_state.value
                if isinstance(access_state, Enum)
                else str(access_state or "Accessible")
            )
            if access_state_str.strip().lower() != "blocked":
                all_blocked = False

            src = getattr(rec, "source_url", "") or getattr(rec, "canonical_url", "")
            if not src and isinstance(rec, dict):
                src = rec.get("source_url") or rec.get("canonical_url", "")
            if not first_source_url and src:
                first_source_url = src

            extracted = self.extract_from_crawl_record(rec)
            # Update store.name if not found yet or higher confidence
            if extracted.is_found("store.name"):
                if combined_records["store.name"].value is None or extracted["store.name"].confidence > combined_records["store.name"].confidence:
                    combined_records["store.name"] = extracted["store.name"]

            # Update store.about_text if not found yet or higher confidence
            if extracted.is_found("store.about_text"):
                if combined_records["store.about_text"].value is None or extracted["store.about_text"].confidence > combined_records["store.about_text"].confidence:
                    combined_records["store.about_text"] = extracted["store.about_text"]

        if record_count > 0 and all_blocked:
            for fld in SUPPORTED_STORE_FIELDS:
                combined_records[fld] = EvidenceRecord(
                    field=fld,
                    value=None,
                    status=EvidenceStatus.BLOCKED,
                    source_url=first_source_url,
                    observed_at=now,
                    method=EvidenceMethod.DOM,
                    confidence=self.confidence,
                )
        elif first_source_url:
            for fld in SUPPORTED_STORE_FIELDS:
                if not combined_records[fld].source_url:
                    combined_records[fld].source_url = first_source_url

        return ExtractedStoreDetails(records=combined_records)

    def _extract_store_name(
        self,
        soup: BeautifulSoup,
    ) -> tuple[str | None, EvidenceMethod, float]:
        """Extract public store name using hierarchy: JSON-LD -> Meta -> Header/Logo -> Title."""
        # 1. JSON-LD Organization / WebSite
        json_name = self._extract_json_ld_name(soup)
        if json_name:
            return json_name, EvidenceMethod.JSON_LD, 0.95

        # 2. Meta tags: og:site_name, application-name
        meta_name = self._extract_meta_name(soup)
        if meta_name:
            return meta_name, EvidenceMethod.META, 0.90

        # 3. Header / Logo text
        header_name = self._extract_header_logo_name(soup)
        if header_name:
            return header_name, EvidenceMethod.DOM, 0.85

        # 4. <title> tag
        title_name = self._extract_title_name(soup)
        if title_name:
            return title_name, EvidenceMethod.DOM, 0.80

        return None, EvidenceMethod.DOM, self.confidence

    def _extract_json_ld_name(self, soup: BeautifulSoup) -> str | None:
        """Inspect JSON-LD scripts for Organization, Store, LocalBusiness, or WebSite name."""
        scripts = soup.find_all(
            "script",
            type=lambda t: t and "application/ld+json" in t.lower(),
        )
        for s in scripts:
            content = s.string or s.get_text()
            if not content or not content.strip():
                continue
            try:
                data = json.loads(content)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue

            candidates = self._find_name_in_json(data)
            if candidates:
                return candidates[0]
        return None

    def _find_name_in_json(self, data: Any) -> list[str]:
        names: list[str] = []
        if isinstance(data, list):
            for item in data:
                names.extend(self._find_name_in_json(item))
        elif isinstance(data, dict):
            if "@graph" in data:
                names.extend(self._find_name_in_json(data["@graph"]))

            raw_type = data.get("@type", "")
            type_list = raw_type if isinstance(raw_type, list) else [raw_type]
            norm_types = {str(t).lower().replace("https://schema.org/", "").replace("http://schema.org/", "") for t in type_list}

            target_types = {"organization", "store", "onlinestore", "localbusiness", "website", "brand"}
            if norm_types.intersection(target_types):
                name_val = data.get("name") or data.get("legalName")
                if isinstance(name_val, str) and name_val.strip():
                    clean_name = self._clean_whitespace(name_val)
                    if clean_name and not self._is_generic_noise(clean_name):
                        names.append(clean_name)
        return names

    def _extract_meta_name(self, soup: BeautifulSoup) -> str | None:
        """Inspect meta tags for og:site_name or application-name."""
        # 1. og:site_name
        og_tag = soup.find(
            "meta",
            property=lambda p: p and p.lower() == "og:site_name",
        )
        if og_tag and og_tag.get("content"):
            val = self._clean_whitespace(og_tag["content"])
            if val and not self._is_generic_noise(val):
                return val

        # 2. application-name
        app_tag = soup.find(
            "meta",
            attrs={"name": lambda n: n and n.lower() == "application-name"},
        )
        if app_tag and app_tag.get("content"):
            val = self._clean_whitespace(app_tag["content"])
            if val and not self._is_generic_noise(val):
                return val

        return None

    def _extract_header_logo_name(self, soup: BeautifulSoup) -> str | None:
        """Extract brand text from header/navbar or logo img alt."""
        header = soup.find(["header", "nav"]) or soup

        # 1. Look for logo/brand text elements
        logo_selectors = (
            '[class*="site-title"]',
            '[class*="header__logo-text"]',
            '[class*="brand-name"]',
            '[class*="logo-text"]',
            '[class*="navbar-brand"]',
            "a.brand",
            "a.logo",
            ".site-header__logo",
            ".site-logo",
        )
        for sel in logo_selectors:
            for el in header.select(sel):
                text = self._clean_whitespace(el.get_text())
                if text and not self._is_generic_noise(text):
                    return text

        # 2. Look for logo img alt
        logo_img = header.select_one(
            'img[class*="logo"], [class*="logo"] img, img[alt*="logo" i], .brand img'
        )
        if logo_img and logo_img.get("alt"):
            alt_text = self._clean_whitespace(logo_img["alt"])
            # Strip trailing/leading 'logo' (e.g. 'Acme Store Logo' -> 'Acme Store')
            cleaned_alt = re.sub(r"(?i)\s*logo$", "", alt_text).strip()
            if cleaned_alt and not self._is_generic_noise(cleaned_alt):
                return cleaned_alt

        return None

    def _extract_title_name(self, soup: BeautifulSoup) -> str | None:
        """Extract store name from <title> tag by removing slogans and page qualifiers."""
        title_tag = soup.find("title")
        if not title_tag:
            return None

        raw_title = self._clean_whitespace(title_tag.get_text())
        if not raw_title:
            return None

        # Split on common title separators: |, —, –, -, •
        parts = re.split(r"\s*[|—–•]\s*", raw_title)
        if len(parts) > 1:
            for part in parts:
                p_clean = part.strip()
                if p_clean and not self._is_generic_noise(p_clean):
                    return p_clean

        # Hyphen split if meaningful
        hyphen_parts = re.split(r"\s+-\s+", raw_title)
        if len(hyphen_parts) > 1:
            for part in hyphen_parts:
                p_clean = part.strip()
                if p_clean and not self._is_generic_noise(p_clean):
                    return p_clean

        if not self._is_generic_noise(raw_title):
            return raw_title

        return None

    def _extract_about_text(
        self,
        soup: BeautifulSoup,
        page_type: str | None = None,
    ) -> tuple[str | None, EvidenceMethod, float]:
        """Extract public About/Contact text from dedicated pages or sections."""
        is_about_page = bool(page_type and page_type.lower() in ("about", "contact"))

        # 1. Prioritize About-specific selectors
        about_selectors = (
            '[class*="about-us"]',
            '[id*="about-us"]',
            '[class*="our-story"]',
            '[id*="our-story"]',
            '[class*="about-content"]',
            '[class*="about_text"]',
            '[class*="about-section"]',
        )
        for sel in about_selectors:
            el = soup.select_one(sel)
            if el:
                text = self._extract_clean_element_text(el)
                if text and len(text) > 15:
                    return text, EvidenceMethod.DOM, 0.95

        # 2. If on an About or Contact page, inspect main/article
        if is_about_page:
            container = soup.find(["main", "article"]) or soup.find(attrs={"role": "main"})
            if container:
                text = self._extract_clean_element_text(container)
                if text and len(text) > 20:
                    return text, EvidenceMethod.DOM, 0.90

        # 3. Fallback to Contact section selectors
        contact_selectors = (
            '[class*="contact-info"]',
            '[class*="contact-us"]',
            '[class*="contact-details"]',
        )
        for sel in contact_selectors:
            el = soup.select_one(sel)
            if el:
                text = self._extract_clean_element_text(el)
                if text and len(text) > 15:
                    return text, EvidenceMethod.DOM, 0.80

        return None, EvidenceMethod.DOM, self.confidence

    def _extract_clean_element_text(self, el: Tag) -> str:
        """Isolate readable text, decomposing scripts, forms, and headers/footers."""
        temp_soup = BeautifulSoup(str(el), "html.parser")
        root = temp_soup.find()
        if not root or not isinstance(root, Tag):
            return ""

        # Decompose non-content or interactive visitor elements
        for unwanted in root.find_all(["script", "style", "form", "nav", "input", "button", "select"]):
            unwanted.decompose()

        raw = root.get_text(separator=" ")
        cleaned = self._clean_whitespace(raw)
        # Cap text length to prevent excessively large blobs
        if len(cleaned) > 1000:
            cleaned = cleaned[:997].rsplit(" ", 1)[0] + "..."
        return cleaned

    def _clean_whitespace(self, text: str | None) -> str:
        if not text:
            return ""
        return re.sub(r"\s+", " ", text).strip()

    def _is_generic_noise(self, text: str) -> bool:
        lower = text.lower().strip()
        if not lower:
            return True
        for noise in GENERIC_TITLE_NOISE:
            if lower == noise or lower.startswith(noise):
                return True
        return False

    def _build_empty_result(
        self,
        source_url: str,
        observed_at: datetime,
    ) -> ExtractedStoreDetails:
        records: dict[str, EvidenceRecord] = {}
        for fld in SUPPORTED_STORE_FIELDS:
            records[fld] = EvidenceRecord(
                field=fld,
                value=None,
                status=EvidenceStatus.NOT_OBSERVED,
                source_url=source_url,
                observed_at=observed_at,
                method=EvidenceMethod.DOM,
                confidence=self.confidence,
            )
        return ExtractedStoreDetails(records=records)


def extract_store_details(
    html: str,
    source_url: str = "",
    observed_at: datetime | None = None,
    page_type: str | None = None,
    confidence: float = 0.85,
) -> ExtractedStoreDetails:
    """Convenience helper to extract store details from HTML."""
    extractor = StoreExtractor(confidence=confidence)
    return extractor.extract_from_html(
        html=html,
        source_url=source_url,
        observed_at=observed_at,
        page_type=page_type,
    )
