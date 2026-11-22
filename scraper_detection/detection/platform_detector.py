"""E-Commerce Platform Detector (Developer 3 - Scraping & Detection).

Deterministic technology detection for Shopify, WooCommerce, and Magento using
scripts, asset paths, HTML markers, and public signals.
Strictly adheres to the EvidenceRecord contract and never fabricates or guesses platforms.
"""

from __future__ import annotations

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


@dataclass(frozen=True)
class PlatformFingerprintRule:
    """Explicit, maintainable definition of a single platform fingerprint rule."""

    platform: str
    signal_type: str  # "script_url", "asset_url", "meta_tag", "html_attribute", "html_class", "inline_script"
    indicator_name: str
    pattern: str
    strength: str  # "strong", "medium", "weak"
    is_regex: bool = False
    method: EvidenceMethod = EvidenceMethod.DOM


@dataclass(frozen=True)
class FingerprintIndicator:
    """Represents a matched fingerprint rule during page inspection."""

    platform: str
    signal_type: str
    indicator_name: str
    matched_value: str
    strength: str  # "strong", "medium", "weak"
    method: EvidenceMethod


# Canonical platform names
PLATFORM_SHOPIFY = "Shopify"
PLATFORM_WOOCOMMERCE = "WooCommerce"
PLATFORM_MAGENTO = "Magento"

# Structured fingerprint dictionary
PLATFORM_RULES: tuple[PlatformFingerprintRule, ...] = (
    # ------------------ SHOPIFY RULES ------------------
    PlatformFingerprintRule(
        platform=PLATFORM_SHOPIFY,
        signal_type="script_url",
        indicator_name="shopify_cdn_script",
        pattern=r"cdn\.shopify\.com/(?:s/files/|shopifycloud/)",
        strength="strong",
        is_regex=True,
        method=EvidenceMethod.URL,
    ),
    PlatformFingerprintRule(
        platform=PLATFORM_SHOPIFY,
        signal_type="asset_url",
        indicator_name="shopify_cdn_asset",
        pattern="cdn.shopify.com",
        strength="strong",
        is_regex=False,
        method=EvidenceMethod.URL,
    ),
    PlatformFingerprintRule(
        platform=PLATFORM_SHOPIFY,
        signal_type="meta_tag",
        indicator_name="shopify_meta_wallet",
        pattern="shopify-digital-wallet",
        strength="strong",
        is_regex=False,
        method=EvidenceMethod.META,
    ),
    PlatformFingerprintRule(
        platform=PLATFORM_SHOPIFY,
        signal_type="meta_tag",
        indicator_name="shopify_meta_checkout_api",
        pattern="shopify-checkout-api-token",
        strength="strong",
        is_regex=False,
        method=EvidenceMethod.META,
    ),
    PlatformFingerprintRule(
        platform=PLATFORM_SHOPIFY,
        signal_type="inline_script",
        indicator_name="shopify_window_object",
        pattern=r"(?:window\s*\.\s*Shopify\s*=|var\s+Shopify\s*=|Shopify\.theme\s*=)",
        strength="strong",
        is_regex=True,
        method=EvidenceMethod.REGEX,
    ),
    PlatformFingerprintRule(
        platform=PLATFORM_SHOPIFY,
        signal_type="html_attribute",
        indicator_name="shopify_section_id",
        pattern=r"shopify-section-",
        strength="strong",
        is_regex=True,
        method=EvidenceMethod.DOM,
    ),
    PlatformFingerprintRule(
        platform=PLATFORM_SHOPIFY,
        signal_type="html_class",
        indicator_name="shopify_section_class",
        pattern="shopify-section",
        strength="strong",
        is_regex=False,
        method=EvidenceMethod.DOM,
    ),
    PlatformFingerprintRule(
        platform=PLATFORM_SHOPIFY,
        signal_type="html_class",
        indicator_name="shopify_payment_button",
        pattern="shopify-payment-button",
        strength="medium",
        is_regex=False,
        method=EvidenceMethod.DOM,
    ),
    PlatformFingerprintRule(
        platform=PLATFORM_SHOPIFY,
        signal_type="html_attribute",
        indicator_name="shopify_data_attribute",
        pattern="data-shopify",
        strength="strong",
        is_regex=False,
        method=EvidenceMethod.DOM,
    ),
    PlatformFingerprintRule(
        platform=PLATFORM_SHOPIFY,
        signal_type="form_action",
        indicator_name="shopify_cart_add_action",
        pattern="/cart/add",
        strength="weak",
        is_regex=False,
        method=EvidenceMethod.DOM,
    ),
    # ------------------ WOOCOMMERCE RULES ------------------
    PlatformFingerprintRule(
        platform=PLATFORM_WOOCOMMERCE,
        signal_type="meta_tag",
        indicator_name="woocommerce_generator_meta",
        pattern=r"WooCommerce(?:\s+[\d.]+)?",
        strength="strong",
        is_regex=True,
        method=EvidenceMethod.META,
    ),
    PlatformFingerprintRule(
        platform=PLATFORM_WOOCOMMERCE,
        signal_type="script_url",
        indicator_name="woocommerce_plugin_script",
        pattern="/wp-content/plugins/woocommerce/",
        strength="strong",
        is_regex=False,
        method=EvidenceMethod.URL,
    ),
    PlatformFingerprintRule(
        platform=PLATFORM_WOOCOMMERCE,
        signal_type="asset_url",
        indicator_name="woocommerce_plugin_asset",
        pattern="/wp-content/plugins/woocommerce/",
        strength="strong",
        is_regex=False,
        method=EvidenceMethod.URL,
    ),
    PlatformFingerprintRule(
        platform=PLATFORM_WOOCOMMERCE,
        signal_type="html_class",
        indicator_name="woocommerce_body_class",
        pattern=r"\bwoocommerce(?:-page|-no-js)?\b",
        strength="strong",
        is_regex=True,
        method=EvidenceMethod.DOM,
    ),
    PlatformFingerprintRule(
        platform=PLATFORM_WOOCOMMERCE,
        signal_type="html_class",
        indicator_name="woocommerce_price_amount_class",
        pattern="woocommerce-Price-amount",
        strength="strong",
        is_regex=False,
        method=EvidenceMethod.DOM,
    ),
    PlatformFingerprintRule(
        platform=PLATFORM_WOOCOMMERCE,
        signal_type="inline_script",
        indicator_name="woocommerce_params_script",
        pattern=r"(?:wc_add_to_cart_params|woocommerce_params|window\.wc\b)",
        strength="strong",
        is_regex=True,
        method=EvidenceMethod.REGEX,
    ),
    PlatformFingerprintRule(
        platform=PLATFORM_WOOCOMMERCE,
        signal_type="html_class",
        indicator_name="woocommerce_loop_product",
        pattern="woocommerce-loop-product",
        strength="medium",
        is_regex=False,
        method=EvidenceMethod.DOM,
    ),
    PlatformFingerprintRule(
        platform=PLATFORM_WOOCOMMERCE,
        signal_type="html_class",
        indicator_name="wc_block_grid",
        pattern="wc-block-grid",
        strength="medium",
        is_regex=False,
        method=EvidenceMethod.DOM,
    ),
    PlatformFingerprintRule(
        platform=PLATFORM_WOOCOMMERCE,
        signal_type="html_class",
        indicator_name="wp_content_class",
        pattern="wp-content",
        strength="weak",
        is_regex=False,
        method=EvidenceMethod.DOM,
    ),
    # ------------------ MAGENTO RULES ------------------
    PlatformFingerprintRule(
        platform=PLATFORM_MAGENTO,
        signal_type="html_attribute",
        indicator_name="magento_data_mage_init",
        pattern="data-mage-init",
        strength="strong",
        is_regex=False,
        method=EvidenceMethod.DOM,
    ),
    PlatformFingerprintRule(
        platform=PLATFORM_MAGENTO,
        signal_type="html_attribute",
        indicator_name="magento_text_x_init_script",
        pattern="text/x-magento-init",
        strength="strong",
        is_regex=False,
        method=EvidenceMethod.DOM,
    ),
    PlatformFingerprintRule(
        platform=PLATFORM_MAGENTO,
        signal_type="script_url",
        indicator_name="magento_static_frontend_script",
        pattern=r"/static/(?:version\d+/)?frontend/",
        strength="strong",
        is_regex=True,
        method=EvidenceMethod.URL,
    ),
    PlatformFingerprintRule(
        platform=PLATFORM_MAGENTO,
        signal_type="script_url",
        indicator_name="magento_mage_js_script",
        pattern=r"mage/(?:cookies|apply/main|translate|common)\.js",
        strength="strong",
        is_regex=True,
        method=EvidenceMethod.URL,
    ),
    PlatformFingerprintRule(
        platform=PLATFORM_MAGENTO,
        signal_type="asset_url",
        indicator_name="magento_pub_static_asset",
        pattern="/pub/static/",
        strength="medium",
        is_regex=False,
        method=EvidenceMethod.URL,
    ),
    PlatformFingerprintRule(
        platform=PLATFORM_MAGENTO,
        signal_type="form_attribute",
        indicator_name="magento_form_key",
        pattern="form_key",
        strength="medium",
        is_regex=False,
        method=EvidenceMethod.DOM,
    ),
    PlatformFingerprintRule(
        platform=PLATFORM_MAGENTO,
        signal_type="html_class",
        indicator_name="magento_body_view_class",
        pattern=r"\b(?:catalog-product-view|catalog-category-view|cms-index-index)\b",
        strength="weak",
        is_regex=True,
        method=EvidenceMethod.DOM,
    ),
)


@dataclass
class PlatformDetectionResult:
    """Outcome of e-commerce platform detection containing evidence and matched indicators."""

    evidence: EvidenceRecord
    platform: str | None
    matched_indicators: list[FingerprintIndicator] = field(default_factory=list)
    confidence_breakdown: dict[str, Any] = field(default_factory=dict)

    def to_evidence(self) -> EvidenceRecord:
        return self.evidence

    @property
    def is_found(self) -> bool:
        return self.evidence.status == EvidenceStatus.FOUND

    @property
    def is_unverified(self) -> bool:
        return self.evidence.status == EvidenceStatus.UNVERIFIED


class PlatformDetector:
    """Deterministic platform detector for Shopify, WooCommerce, and Magento."""

    def __init__(self, rules: Sequence[PlatformFingerprintRule] = PLATFORM_RULES) -> None:
        self.rules = tuple(rules)

    def detect_from_html(
        self,
        html: str,
        source_url: str = "",
        observed_at: datetime | None = None,
        script_urls: Sequence[str] | None = None,
    ) -> PlatformDetectionResult:
        """Detect e-commerce platform from rendered HTML and asset URLs."""
        if observed_at is None:
            observed_at = datetime.now(timezone.utc)

        if not html or not html.strip():
            empty_evidence = EvidenceRecord(
                field="technology.ecommerce_platform",
                value=None,
                status=EvidenceStatus.NOT_FOUND,
                source_url=source_url,
                observed_at=observed_at,
                method=EvidenceMethod.DOM,
                confidence=1.0,
            )
            return PlatformDetectionResult(
                evidence=empty_evidence,
                platform=None,
                matched_indicators=[],
                confidence_breakdown={"total_matches": 0},
            )

        soup = BeautifulSoup(html, "html.parser")

        # 1. Collect all matching indicators across all platform rules
        matched_indicators = self._collect_matched_indicators(soup, html, script_urls)

        # 2. Score platforms and determine primary candidate
        result = self._evaluate_platform_scores(
            matched_indicators=matched_indicators,
            source_url=source_url,
            observed_at=observed_at,
        )

        return result

    def detect_from_crawl_record(self, record: Any) -> PlatformDetectionResult:
        """Detect platform from a D2 CrawlRecord object, dict, or duck-type."""
        now = datetime.now(timezone.utc)
        if record is None:
            return self.detect_from_html("", "", now)

        # Respect access_state
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
            observed_at = now

        # Inaccessible / blocked pages yield BLOCKED
        if access_state_str.strip().lower() != "accessible":
            evidence = EvidenceRecord(
                field="technology.ecommerce_platform",
                value=None,
                status=EvidenceStatus.BLOCKED,
                source_url=source_url,
                observed_at=observed_at,
                method=EvidenceMethod.DOM,
                confidence=1.0,
            )
            return PlatformDetectionResult(
                evidence=evidence,
                platform=None,
                matched_indicators=[],
                confidence_breakdown={"reason": f"Page access state is {access_state_str}"},
            )

        html = getattr(record, "rendered_html", "")
        if not html and isinstance(record, dict):
            html = record.get("rendered_html", "")

        script_urls = getattr(record, "script_urls", None)
        if script_urls is None and isinstance(record, dict):
            script_urls = record.get("script_urls")

        return self.detect_from_html(
            html=html,
            source_url=source_url,
            observed_at=observed_at,
            script_urls=script_urls,
        )

    def detect_from_crawl_records(self, records: Iterable[Any]) -> PlatformDetectionResult:
        """Aggregate platform detection indicators across multiple CrawlRecords (e.g. CrawlBundle)."""
        all_matched_indicators: list[FingerprintIndicator] = []
        best_source_url = ""
        earliest_time = datetime.now(timezone.utc)

        for rec in records:
            res = self.detect_from_crawl_record(rec)
            if res.matched_indicators:
                if not best_source_url:
                    best_source_url = res.evidence.source_url
                all_matched_indicators.extend(res.matched_indicators)

        # Deduplicate indicators by (platform, indicator_name, matched_value)
        seen_keys: set[tuple[str, str, str]] = set()
        deduped_indicators: list[FingerprintIndicator] = []
        for ind in all_matched_indicators:
            key = (ind.platform, ind.indicator_name, ind.matched_value)
            if key not in seen_keys:
                seen_keys.add(key)
                deduped_indicators.append(ind)

        return self._evaluate_platform_scores(
            matched_indicators=deduped_indicators,
            source_url=best_source_url,
            observed_at=earliest_time,
        )

    def _collect_matched_indicators(
        self,
        soup: BeautifulSoup,
        raw_html: str,
        extra_script_urls: Sequence[str] | None = None,
    ) -> list[FingerprintIndicator]:
        """Inspect HTML, scripts, assets, and metadata against all platform rules."""
        matched: list[FingerprintIndicator] = []

        # Gather page asset URLs
        script_srcs = [
            s["src"].strip() for s in soup.find_all("script", src=True) if s.get("src")
        ]
        if extra_script_urls:
            script_srcs.extend(extra_script_urls)

        link_hrefs = [
            lnk["href"].strip() for lnk in soup.find_all("link", href=True) if lnk.get("href")
        ]
        all_asset_urls = script_srcs + link_hrefs

        # Gather meta tags
        meta_tags = soup.find_all("meta")

        # Gather inline scripts text
        inline_scripts = [
            s.string or s.get_text()
            for s in soup.find_all("script")
            if not s.get("src") and (s.string or s.get_text())
        ]
        inline_scripts_blob = "\n".join(inline_scripts)

        # Gather body classes
        body_tag = soup.find("body")
        body_classes = " ".join(body_tag.get("class", [])) if body_tag and isinstance(body_tag.get("class"), list) else str(body_tag.get("class", "") if body_tag else "")

        for rule in self.rules:
            # 1. script_url rules
            if rule.signal_type == "script_url":
                for src in script_srcs:
                    if self._matches_pattern(src, rule.pattern, rule.is_regex):
                        matched.append(
                            FingerprintIndicator(
                                platform=rule.platform,
                                signal_type=rule.signal_type,
                                indicator_name=rule.indicator_name,
                                matched_value=src,
                                strength=rule.strength,
                                method=rule.method,
                            )
                        )
                        break

            # 2. asset_url rules
            elif rule.signal_type == "asset_url":
                for asset in all_asset_urls:
                    if self._matches_pattern(asset, rule.pattern, rule.is_regex):
                        matched.append(
                            FingerprintIndicator(
                                platform=rule.platform,
                                signal_type=rule.signal_type,
                                indicator_name=rule.indicator_name,
                                matched_value=asset,
                                strength=rule.strength,
                                method=rule.method,
                            )
                        )
                        break

            # 3. meta_tag rules
            elif rule.signal_type == "meta_tag":
                for meta in meta_tags:
                    meta_str = " ".join(
                        f"{k}={v}" for k, v in meta.attrs.items() if isinstance(v, str)
                    )
                    if self._matches_pattern(meta_str, rule.pattern, rule.is_regex):
                        matched.append(
                            FingerprintIndicator(
                                platform=rule.platform,
                                signal_type=rule.signal_type,
                                indicator_name=rule.indicator_name,
                                matched_value=meta_str,
                                strength=rule.strength,
                                method=rule.method,
                            )
                        )
                        break

            # 4. inline_script rules
            elif rule.signal_type == "inline_script":
                if inline_scripts_blob and self._matches_pattern(inline_scripts_blob, rule.pattern, rule.is_regex):
                    matched.append(
                        FingerprintIndicator(
                            platform=rule.platform,
                            signal_type=rule.signal_type,
                            indicator_name=rule.indicator_name,
                            matched_value=rule.pattern,
                            strength=rule.strength,
                            method=rule.method,
                        )
                    )

            # 5. html_class rules
            elif rule.signal_type == "html_class":
                # Check in body class or any tag with matching class
                if self._matches_pattern(body_classes, rule.pattern, rule.is_regex):
                    matched.append(
                        FingerprintIndicator(
                            platform=rule.platform,
                            signal_type=rule.signal_type,
                            indicator_name=rule.indicator_name,
                            matched_value=body_classes,
                            strength=rule.strength,
                            method=rule.method,
                        )
                    )
                else:
                    # Check if any element in DOM has matching class
                    for el in soup.find_all(attrs={"class": True}):
                        cls_str = " ".join(el.get("class", [])) if isinstance(el.get("class"), list) else str(el.get("class", ""))
                        if self._matches_pattern(cls_str, rule.pattern, rule.is_regex):
                            matched.append(
                                FingerprintIndicator(
                                    platform=rule.platform,
                                    signal_type=rule.signal_type,
                                    indicator_name=rule.indicator_name,
                                    matched_value=cls_str,
                                    strength=rule.strength,
                                    method=rule.method,
                                )
                            )
                            break

            # 6. html_attribute rules
            elif rule.signal_type == "html_attribute":
                # Check tag attributes or raw HTML markers
                has_attr = False
                for el in soup.find_all(True):
                    for attr_name, attr_val in el.attrs.items():
                        full_attr = f"{attr_name}={attr_val}"
                        if self._matches_pattern(full_attr, rule.pattern, rule.is_regex) or self._matches_pattern(attr_name, rule.pattern, rule.is_regex):
                            matched.append(
                                FingerprintIndicator(
                                    platform=rule.platform,
                                    signal_type=rule.signal_type,
                                    indicator_name=rule.indicator_name,
                                    matched_value=full_attr,
                                    strength=rule.strength,
                                    method=rule.method,
                                )
                            )
                            has_attr = True
                            break
                    if has_attr:
                        break

            # 7. form_action or form_attribute rules
            elif rule.signal_type in ("form_action", "form_attribute"):
                for form in soup.find_all("form"):
                    action = form.get("action", "")
                    if self._matches_pattern(action, rule.pattern, rule.is_regex):
                        matched.append(
                            FingerprintIndicator(
                                platform=rule.platform,
                                signal_type=rule.signal_type,
                                indicator_name=rule.indicator_name,
                                matched_value=action,
                                strength=rule.strength,
                                method=rule.method,
                            )
                        )
                        break
                    # Also check inputs inside form
                    for inp in form.find_all("input"):
                        inp_str = " ".join(f"{k}={v}" for k, v in inp.attrs.items())
                        if self._matches_pattern(inp_str, rule.pattern, rule.is_regex):
                            matched.append(
                                FingerprintIndicator(
                                    platform=rule.platform,
                                    signal_type=rule.signal_type,
                                    indicator_name=rule.indicator_name,
                                    matched_value=inp_str,
                                    strength=rule.strength,
                                    method=rule.method,
                                )
                            )
                            break

        return matched

    def _matches_pattern(self, target: str, pattern: str, is_regex: bool) -> bool:
        """Match pattern against target string deterministically."""
        if not target:
            return False
        if is_regex:
            return bool(re.search(pattern, target, flags=re.IGNORECASE))
        return pattern.lower() in target.lower()

    def _evaluate_platform_scores(
        self,
        matched_indicators: list[FingerprintIndicator],
        source_url: str,
        observed_at: datetime,
    ) -> PlatformDetectionResult:
        """Group indicators by platform, calculate confidence, and assign EvidenceStatus."""
        if not matched_indicators:
            evidence = EvidenceRecord(
                field="technology.ecommerce_platform",
                value=None,
                status=EvidenceStatus.NOT_FOUND,
                source_url=source_url,
                observed_at=observed_at,
                method=EvidenceMethod.DOM,
                confidence=1.0,
            )
            return PlatformDetectionResult(
                evidence=evidence,
                platform=None,
                matched_indicators=[],
                confidence_breakdown={"platform_scores": {}},
            )

        # Group indicators by platform
        platform_groups: dict[str, list[FingerprintIndicator]] = {}
        for ind in matched_indicators:
            platform_groups.setdefault(ind.platform, []).append(ind)

        platform_scores: dict[str, dict[str, Any]] = {}
        for plat, inds in platform_groups.items():
            strong_count = sum(1 for i in inds if i.strength == "strong")
            medium_count = sum(1 for i in inds if i.strength == "medium")
            weak_count = sum(1 for i in inds if i.strength == "weak")

            confidence = self._compute_platform_confidence(
                strong=strong_count,
                medium=medium_count,
                weak=weak_count,
            )

            # Determine dominant method from indicators
            method_counts: dict[EvidenceMethod, int] = {}
            for i in inds:
                method_counts[i.method] = method_counts.get(i.method, 0) + (3 if i.strength == "strong" else 1)
            dominant_method = max(method_counts.items(), key=lambda pair: pair[1])[0]

            platform_scores[plat] = {
                "strong": strong_count,
                "medium": medium_count,
                "weak": weak_count,
                "confidence": confidence,
                "dominant_method": dominant_method,
                "indicators": inds,
            }

        # Sort platforms by confidence descending
        sorted_candidates = sorted(
            platform_scores.items(),
            key=lambda item: item[1]["confidence"],
            reverse=True,
        )

        top_platform, top_info = sorted_candidates[0]
        top_conf = top_info["confidence"]
        top_method = top_info["dominant_method"]

        # Conflict check: If multiple platforms both have strong signals
        strong_platforms = [
            p for p, info in platform_scores.items() if info["strong"] >= 1
        ]
        if len(strong_platforms) > 1:
            # Conflicting evidence -> UNVERIFIED
            evidence = EvidenceRecord(
                field="technology.ecommerce_platform",
                value=top_platform,
                status=EvidenceStatus.UNVERIFIED,
                source_url=source_url,
                observed_at=observed_at,
                method=top_method,
                confidence=0.50,
            )
            return PlatformDetectionResult(
                evidence=evidence,
                platform=top_platform,
                matched_indicators=matched_indicators,
                confidence_breakdown={
                    "platform_scores": platform_scores,
                    "conflict": True,
                    "reason": f"Conflicting strong signals for {strong_platforms}",
                },
            )

        # Sufficient evidence check:
        # Requires at least 1 strong signal or >= 2 medium signals (confidence >= 0.70)
        if top_conf >= 0.70 and top_info["strong"] >= 1 or (top_info["medium"] >= 2):
            evidence = EvidenceRecord(
                field="technology.ecommerce_platform",
                value=top_platform,
                status=EvidenceStatus.FOUND,
                source_url=source_url,
                observed_at=observed_at,
                method=top_method,
                confidence=top_conf,
            )
        else:
            # Ambiguous or weak evidence (e.g. only 1 medium or 1 weak signal) -> UNVERIFIED
            evidence = EvidenceRecord(
                field="technology.ecommerce_platform",
                value=top_platform,
                status=EvidenceStatus.UNVERIFIED,
                source_url=source_url,
                observed_at=observed_at,
                method=top_method,
                confidence=top_conf,
            )

        return PlatformDetectionResult(
            evidence=evidence,
            platform=top_platform,
            matched_indicators=top_info["indicators"],
            confidence_breakdown={
                "platform_scores": platform_scores,
                "conflict": False,
            },
        )

    def _compute_platform_confidence(
        self,
        strong: int,
        medium: int,
        weak: int,
    ) -> float:
        """Deterministic confidence score between 0.0 and 1.0 based on signal strength."""
        if strong >= 2:
            conf = 0.95 + min(0.03, medium * 0.01)
        elif strong == 1:
            conf = 0.85 + min(0.10, medium * 0.05 + weak * 0.02)
        elif medium >= 2:
            conf = 0.75 + min(0.15, (medium - 2) * 0.05 + weak * 0.02)
        elif medium == 1:
            conf = 0.55 + min(0.05, weak * 0.02)
        elif weak >= 1:
            conf = 0.35 + min(0.10, (weak - 1) * 0.05)
        else:
            conf = 0.0

        return round(min(conf, 1.0), 2)


def detect_ecommerce_platform(
    html: str,
    source_url: str = "",
    observed_at: datetime | None = None,
    script_urls: Sequence[str] | None = None,
) -> PlatformDetectionResult:
    """Convenience helper to detect e-commerce platform from HTML."""
    detector = PlatformDetector()
    return detector.detect_from_html(
        html=html,
        source_url=source_url,
        observed_at=observed_at,
        script_urls=script_urls,
    )
