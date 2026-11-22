"""Contact and Social Profile Extractor (Developer 3 - Scraping & Detection).

Deterministic extraction of public business contact details (email, phone)
and official social profile links (Instagram, Facebook, YouTube, X/Twitter, LinkedIn)
using BeautifulSoup4, Python re, and urllib.parse.
Strictly adheres to the EvidenceRecord contract and never invents or guesses facts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Sequence
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from scraper_detection.schemas.evidence import (
    EvidenceMethod,
    EvidenceRecord,
    EvidenceStatus,
)

SUPPORTED_CONTACT_FIELDS: tuple[str, ...] = (
    "contact.email",
    "contact.phone",
    "social.instagram",
    "social.facebook",
    "social.youtube",
    "social.twitter",
    "social.linkedin",
)

# Obvious noise domains and dummy emails to exclude
DISALLOWED_EMAIL_DOMAINS: set[str] = {
    "example.com",
    "example.org",
    "example.net",
    "domain.com",
    "yoursite.com",
    "email.com",
    "test.com",
    "sample.com",
    "dummy.com",
    "myshopify.com",
    "sentry.io",
    "wixpress.com",
    "github.com",
    "schema.org",
    "w3.org",
}

# Image / code asset extensions mistakenly matching email regex (e.g. icon@2x.png)
DISALLOWED_EMAIL_EXTENSIONS: tuple[str, ...] = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".css",
    ".js",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
)

# Prioritized business email prefixes
PREFERRED_EMAIL_PREFIXES: tuple[str, ...] = (
    "support@",
    "info@",
    "contact@",
    "sales@",
    "hello@",
    "care@",
    "help@",
    "orders@",
    "service@",
    "inquiry@",
    "billing@",
)

# Known social domains
SOCIAL_DOMAINS: dict[str, str] = {
    "instagram": "social.instagram",
    "facebook": "social.facebook",
    "youtube": "social.youtube",
    "twitter": "social.twitter",
    "x": "social.twitter",
    "linkedin": "social.linkedin",
}


@dataclass
class ExtractedContactSocial:
    """Represents extracted contact and social evidence records."""

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


class ContactSocialExtractor:
    """Extracts business contact info and social links deterministically."""

    def __init__(self, confidence: float = 0.85) -> None:
        self.confidence = confidence

    def extract_from_html(
        self,
        html: str,
        source_url: str = "",
        observed_at: datetime | None = None,
    ) -> ExtractedContactSocial:
        """Extract contact (email, phone) and social profiles from HTML string."""
        if observed_at is None:
            observed_at = datetime.now(timezone.utc)

        if not html or not html.strip():
            return self._build_empty_result(source_url, observed_at)

        soup = BeautifulSoup(html, "html.parser")

        # 1. Business Email Extraction
        email, email_method, email_conf = self._extract_business_email(soup)

        # 2. Business Phone Extraction
        phone, phone_method, phone_conf = self._extract_business_phone(soup)

        # 3. Social Profile Links Extraction
        social_links = self._extract_social_links(soup, source_url)

        records: dict[str, EvidenceRecord] = {}

        # contact.email
        records["contact.email"] = EvidenceRecord(
            field="contact.email",
            value=email,
            status=EvidenceStatus.FOUND if email else EvidenceStatus.NOT_OBSERVED,
            source_url=source_url,
            observed_at=observed_at,
            method=email_method if email else EvidenceMethod.REGEX,
            confidence=email_conf if email else self.confidence,
        )

        # contact.phone
        records["contact.phone"] = EvidenceRecord(
            field="contact.phone",
            value=phone,
            status=EvidenceStatus.FOUND if phone else EvidenceStatus.NOT_OBSERVED,
            source_url=source_url,
            observed_at=observed_at,
            method=phone_method if phone else EvidenceMethod.REGEX,
            confidence=phone_conf if phone else self.confidence,
        )

        # social profiles
        for platform_key in ("instagram", "facebook", "youtube", "twitter", "linkedin"):
            field_name = f"social.{platform_key}"
            url_val = social_links.get(platform_key)
            records[field_name] = EvidenceRecord(
                field=field_name,
                value=url_val,
                status=EvidenceStatus.FOUND if url_val else EvidenceStatus.NOT_OBSERVED,
                source_url=source_url,
                observed_at=observed_at,
                method=EvidenceMethod.DOM if url_val else EvidenceMethod.URL,
                confidence=0.95 if url_val else self.confidence,
            )

        return ExtractedContactSocial(records=records)

    def extract_from_crawl_record(self, record: Any) -> ExtractedContactSocial:
        """Extract from a D2 CrawlRecord object, dict, or duck-type."""
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

        # Inaccessible/blocked records produce BLOCKED status
        if access_state_str.strip().lower() != "accessible":
            records: dict[str, EvidenceRecord] = {}
            for fld in SUPPORTED_CONTACT_FIELDS:
                records[fld] = EvidenceRecord(
                    field=fld,
                    value=None,
                    status=EvidenceStatus.BLOCKED,
                    source_url=source_url,
                    observed_at=observed_at,
                    method=EvidenceMethod.DOM,
                    confidence=self.confidence,
                )
            return ExtractedContactSocial(records=records)

        html = getattr(record, "rendered_html", "")
        if not html and isinstance(record, dict):
            html = record.get("rendered_html", "")

        return self.extract_from_html(
            html=html,
            source_url=source_url,
            observed_at=observed_at,
        )

    def extract_from_crawl_records(
        self,
        records: Iterable[Any],
    ) -> ExtractedContactSocial:
        """Aggregate contact details and social links across multiple crawled pages."""
        combined_records: dict[str, EvidenceRecord] = {}
        now = datetime.now(timezone.utc)
        all_blocked = True
        record_count = 0
        first_source_url = ""

        for fld in SUPPORTED_CONTACT_FIELDS:
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
            for fld in SUPPORTED_CONTACT_FIELDS:
                # Update if current aggregated field is not found and page has evidence
                if combined_records[fld].value is None and extracted.is_found(fld):
                    combined_records[fld] = extracted[fld]

        if record_count > 0 and all_blocked:
            for fld in SUPPORTED_CONTACT_FIELDS:
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
            for fld in SUPPORTED_CONTACT_FIELDS:
                if not combined_records[fld].source_url:
                    combined_records[fld].source_url = first_source_url

        return ExtractedContactSocial(records=combined_records)

    def _extract_business_email(
        self,
        soup: BeautifulSoup,
    ) -> tuple[str | None, EvidenceMethod, float]:
        """Extract public business email using mailto: links and text regex."""
        # 1. Search mailto: links
        mailto_links = soup.find_all(
            "a",
            href=lambda h: h and h.lower().startswith("mailto:"),
        )
        for link in mailto_links:
            raw_href = link["href"].strip()
            # Strip mailto: and query parameters (?subject=...)
            email_part = re.sub(r"(?i)^mailto:", "", raw_href)
            email_part = email_part.split("?")[0].strip()
            if self._is_valid_business_email(email_part):
                return email_part, EvidenceMethod.DOM, 0.95

        # 2. Prioritize footer and contact sections
        contact_containers = soup.find_all(
            attrs={"class": lambda c: c and any(w in c.lower() for w in ("contact", "footer", "support", "help"))}
        )
        for container in contact_containers:
            text = container.get_text()
            candidates = self._find_emails_in_text(text)
            if candidates:
                return candidates[0], EvidenceMethod.REGEX, 0.90

        # 3. Scan whole visible page text
        page_text = soup.get_text()
        candidates = self._find_emails_in_text(page_text)
        if candidates:
            return candidates[0], EvidenceMethod.REGEX, 0.85

        return None, EvidenceMethod.REGEX, self.confidence

    def _find_emails_in_text(self, text: str) -> list[str]:
        """Use Python re to find and filter valid business email candidates."""
        if not text:
            return []

        pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
        raw_matches = re.findall(pattern, text)

        valid_emails: list[str] = []
        for em in raw_matches:
            cleaned = em.strip()
            if self._is_valid_business_email(cleaned):
                valid_emails.append(cleaned)

        # Sort: prefer business prefixes like support@, info@, contact@
        def sort_key(email: str) -> int:
            lower = email.lower()
            for idx, pfx in enumerate(PREFERRED_EMAIL_PREFIXES):
                if lower.startswith(pfx):
                    return idx
            return 99

        valid_emails.sort(key=sort_key)
        return valid_emails

    def _is_valid_business_email(self, email: str) -> bool:
        """Deterministically validate email format and reject noise/placeholders."""
        if not email or len(email) < 6 or "@" not in email:
            return False

        lower = email.lower().strip()

        # Check for asset file extensions (e.g. icon@2x.png)
        for ext in DISALLOWED_EMAIL_EXTENSIONS:
            if lower.endswith(ext):
                return False

        # Split user and domain
        parts = lower.split("@", 1)
        if len(parts) != 2:
            return False
        user, domain = parts

        # Reject generic dummy/noise user parts
        if user in ("user", "yourname", "name", "username", "someone", "email", "test"):
            return False

        # Reject disallowed domains
        if domain in DISALLOWED_EMAIL_DOMAINS:
            return False

        # Domain must have at least one period and valid TLD length
        domain_parts = domain.split(".")
        if len(domain_parts) < 2:
            return False
        if len(domain_parts[-1]) < 2 or len(domain_parts[-1]) > 12:
            return False

        return True

    def _extract_business_phone(
        self,
        soup: BeautifulSoup,
    ) -> tuple[str | None, EvidenceMethod, float]:
        """Extract public business phone from tel: links and text regex."""
        # 1. Search tel: links
        tel_links = soup.find_all(
            "a",
            href=lambda h: h and h.lower().startswith("tel:"),
        )
        for link in tel_links:
            raw_href = link["href"].strip()
            phone_part = re.sub(r"(?i)^tel:", "", raw_href)
            phone_part = phone_part.split("?")[0].strip()
            norm_phone = self._normalize_phone(phone_part)
            if self._is_valid_phone(norm_phone):
                return norm_phone, EvidenceMethod.DOM, 0.95

        # 2. Prioritize footer and contact sections
        contact_containers = soup.find_all(
            attrs={"class": lambda c: c and any(w in c.lower() for w in ("contact", "footer", "support", "help", "phone", "header"))}
        )
        for container in contact_containers:
            text = container.get_text()
            candidates = self._find_phones_in_text(text)
            if candidates:
                return candidates[0], EvidenceMethod.REGEX, 0.90

        # 3. Scan whole visible page text
        page_text = soup.get_text()
        candidates = self._find_phones_in_text(page_text)
        if candidates:
            return candidates[0], EvidenceMethod.REGEX, 0.80

        return None, EvidenceMethod.REGEX, self.confidence

    def _find_phones_in_text(self, text: str) -> list[str]:
        """Extract and validate phone number strings from visible text."""
        if not text:
            return []

        # Common phone patterns:
        # - Explicit prefix: Phone: ..., Call: ..., Tel: ...
        # - International: +1 (555) 123-4567, +91 98765 43210, +44 20 7946 0958
        # - US/Standard: 1-800-555-0199, (555) 123-4567, 555-123-4567
        # - Indian/local: +91-9876543210, 080-12345678, 1800 123 4567
        phone_patterns = (
            # Explicit prefix like Phone:, Tel:, Call our office:
            r"(?i)(?:phone|tel|call|contact|toll[- ]?free|helpline|mobile|ph)[^0-9+()]{0,25}?([+]?[0-9\s().-]{7,25})",
            # Standard international with plus
            r"(?<!\w)(\+[0-9]{1,4}[\s.-]?\(?[0-9]{1,4}\)?[\s.-]?[0-9]{2,5}[\s.-]?[0-9]{3,5})",
            # Toll free 1-800 or 1800
            r"(?<!\w)(1[- ]?800[- ][0-9]{3}[- ][0-9]{4})\b",
            r"(?<!\w)(1800[\s.-]?[0-9]{3}[\s.-]?[0-9]{3,4})\b",
            # US with area code: (555) 123-4567 or 555-123-4567
            r"(?<!\w)(\(?[2-9][0-9]{2}\)?[\s.-]?[0-9]{3}[\s.-]?[0-9]{4})\b",
        )

        candidates: list[str] = []
        for pat in phone_patterns:
            matches = re.finditer(pat, text)
            for m in matches:
                raw_match = m.group(1) if m.groups() else m.group(0)
                norm = self._normalize_phone(raw_match)
                if self._is_valid_phone(norm):
                    candidates.append(norm)

        # Deduplicate while preserving order
        seen: set[str] = set()
        deduped: list[str] = []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                deduped.append(c)
        return deduped

    def _normalize_phone(self, phone_str: str) -> str:
        """Conservatively clean whitespace and extraneous outer punctuation."""
        if not phone_str:
            return ""
        cleaned = re.sub(r"\s+", " ", phone_str).strip()
        cleaned = cleaned.strip(".,;:|/ ")
        return cleaned

    def _is_valid_phone(self, phone_str: str) -> bool:
        """Validate digit count and filter out dates, prices, and postal codes."""
        if not phone_str:
            return False

        digits_only = re.sub(r"[^0-9]", "", phone_str)
        num_digits = len(digits_only)

        # Phone numbers must have between 7 and 15 digits
        if num_digits < 7 or num_digits > 15:
            return False

        # Filter out common date patterns: YYYY-MM-DD or DD-MM-YYYY
        if re.match(r"^\d{4}[-/]\d{2}[-/]\d{2}$", phone_str) or re.match(r"^\d{2}[-/]\d{2}[-/]\d{4}$", phone_str):
            return False

        # Filter out prices or percentages
        if any(sym in phone_str for sym in ("$", "₹", "€", "£", "%")):
            return False

        return True

    def _extract_social_links(
        self,
        soup: BeautifulSoup,
        source_url: str,
    ) -> dict[str, str]:
        """Detect and classify official social profile URLs using BeautifulSoup & urllib.parse."""
        profiles: dict[str, str] = {}

        for a in soup.find_all("a", href=True):
            raw_href = a["href"].strip()
            if not raw_href or raw_href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue

            resolved_url = self._resolve_social_url(raw_href, source_url)
            if not resolved_url:
                continue

            parsed = urlparse(resolved_url)
            netloc = parsed.netloc.lower()

            # Strip port and www. or m.
            if ":" in netloc:
                netloc = netloc.split(":")[0]
            if netloc.startswith("www."):
                netloc = netloc[4:]
            elif netloc.startswith("m."):
                netloc = netloc[2:]

            path = parsed.path.strip("/")

            # 1. Instagram
            if netloc in ("instagram.com", "instagr.am"):
                if "instagram" not in profiles and self._is_valid_social_path("instagram", path):
                    profiles["instagram"] = f"https://www.instagram.com/{path}/"

            # 2. Facebook
            elif netloc in ("facebook.com", "fb.com", "fb.me"):
                if "facebook" not in profiles and self._is_valid_social_path("facebook", path):
                    profiles["facebook"] = f"https://www.facebook.com/{path}/"

            # 3. YouTube
            elif netloc in ("youtube.com", "youtu.be"):
                if "youtube" not in profiles and self._is_valid_social_path("youtube", path):
                    profiles["youtube"] = f"https://www.youtube.com/{path}"

            # 4. Twitter / X
            elif netloc in ("twitter.com", "x.com"):
                if "twitter" not in profiles and self._is_valid_social_path("twitter", path):
                    profiles["twitter"] = f"https://x.com/{path}"

            # 5. LinkedIn
            elif netloc == "linkedin.com":
                if "linkedin" not in profiles and self._is_valid_social_path("linkedin", path):
                    profiles["linkedin"] = f"https://www.linkedin.com/{path}"

        return profiles

    def _resolve_social_url(self, href: str, source_url: str) -> str | None:
        """Resolve protocol-relative, relative, or scheme-less social URLs."""
        cleaned = href.strip()
        if not cleaned:
            return None

        # Protocol-relative (//instagram.com/acme)
        if cleaned.startswith("//"):
            return f"https:{cleaned}"

        # Scheme-less social link (e.g. instagram.com/acme)
        for dom in ("instagram.com", "facebook.com", "youtube.com", "twitter.com", "x.com", "linkedin.com"):
            if cleaned.lower().startswith(dom) or cleaned.lower().startswith(f"www.{dom}"):
                return f"https://{cleaned}"

        # Resolve relative against source_url
        if source_url:
            return urljoin(source_url, cleaned)

        return cleaned

    def _is_valid_social_path(self, platform: str, path: str) -> bool:
        """Validate path is a genuine profile/channel and not a share link, login, or home page."""
        if not path:
            return False

        lower_path = path.lower()
        parts = lower_path.split("/")
        first_segment = parts[0]

        if platform == "instagram":
            # Filter non-profile routes
            if first_segment in ("p", "reels", "reel", "stories", "explore", "direct", "accounts", "about", "legal"):
                return False
            return True

        if platform == "facebook":
            if first_segment in ("sharer", "sharer.php", "share", "share.php", "dialog", "tr", "policies", "help", "login", "plugins"):
                return False
            return True

        if platform == "youtube":
            if first_segment in ("watch", "embed", "results", "feed", "share", "playlist"):
                return False
            return True

        if platform == "twitter":
            if first_segment in ("intent", "share", "search", "home", "explore", "notifications", "privacy", "tos", "i"):
                return False
            return True

        if platform == "linkedin":
            if first_segment in ("sharearticle", "sharing", "feed", "login", "signup", "legal"):
                return False
            # Expect company, in, or school
            if first_segment in ("company", "in", "school"):
                return len(parts) >= 2 and bool(parts[1])
            return True

        return True

    def _build_empty_result(
        self,
        source_url: str,
        observed_at: datetime,
    ) -> ExtractedContactSocial:
        records: dict[str, EvidenceRecord] = {}
        for fld in SUPPORTED_CONTACT_FIELDS:
            records[fld] = EvidenceRecord(
                field=fld,
                value=None,
                status=EvidenceStatus.NOT_OBSERVED,
                source_url=source_url,
                observed_at=observed_at,
                method=EvidenceMethod.DOM,
                confidence=self.confidence,
            )
        return ExtractedContactSocial(records=records)


def extract_contact_and_social(
    html: str,
    source_url: str = "",
    observed_at: datetime | None = None,
    confidence: float = 0.85,
) -> ExtractedContactSocial:
    """Convenience helper to extract contact and social info from HTML."""
    extractor = ContactSocialExtractor(confidence=confidence)
    return extractor.extract_from_html(
        html=html,
        source_url=source_url,
        observed_at=observed_at,
    )
