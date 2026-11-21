"""CrawlBundle typed contract independent of Playwright.

Dev3 consumes this data without importing browser automation internals.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import json


class AccessState(str, Enum):
    """Classification of the accessibility state of a target page."""
    ACCESSIBLE = "Accessible"
    BLOCKED = "Blocked"
    UNAVAILABLE = "Unavailable"
    ERROR = "Error"


class PageType(str, Enum):
    """Identified semantic role of the crawled page."""
    HOMEPAGE = "homepage"
    COLLECTION = "collection"
    PRODUCT = "product"
    ABOUT = "about"
    CONTACT = "contact"
    OTHER = "other"


class TriState(str, Enum):
    """Distinguishable observation status for dynamic DOM signals."""
    OBSERVED = "observed"
    NOT_OBSERVED = "not_observed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ObservationMetadata:
    """Dynamic DOM observations captured during inspection.

    Note: Represents visible DOM observations without submitting forms or dismissing dialogs.
    Uses TriState (observed, not_observed, unknown) so unavailable inspections are not treated as false.
    """
    newsletter_form: TriState = TriState.NOT_OBSERVED
    email_input: TriState = TriState.NOT_OBSERVED
    phone_input: TriState = TriState.NOT_OBSERVED
    promotional_popup: TriState = TriState.NOT_OBSERVED
    dialog_modal: TriState = TriState.NOT_OBSERVED
    cookie_banner: TriState = TriState.NOT_OBSERVED
    observed_form_actions: list[str] = field(default_factory=list)
    observed_input_labels: list[str] = field(default_factory=list)
    extra_signals: dict[str, Any] = field(default_factory=dict)

    # Backward-compatible convenience properties
    @property
    def has_newsletter_form(self) -> bool:
        return self.newsletter_form == TriState.OBSERVED

    @property
    def has_email_input(self) -> bool:
        return self.email_input == TriState.OBSERVED

    @property
    def has_phone_input(self) -> bool:
        return self.phone_input == TriState.OBSERVED

    @property
    def has_promotional_popup(self) -> bool:
        return self.promotional_popup == TriState.OBSERVED

    @property
    def has_dialog_modal(self) -> bool:
        return self.dialog_modal == TriState.OBSERVED

    @property
    def has_cookie_banner(self) -> bool:
        return self.cookie_banner == TriState.OBSERVED


@dataclass(frozen=True)
class CrawlRecord:
    """Data captured from a single crawled page."""

    canonical_url: str
    source_url: str
    page_type: PageType
    http_status: int | None
    content_type: str | None
    access_state: AccessState
    fetch_timestamp: str  # ISO 8601 UTC string

    # Rendered content & signals
    rendered_html: str = ""
    visible_text: str = ""
    script_urls: list[str] = field(default_factory=list)

    # Classification & diagnostics
    access_reason: str = ""
    error_message: str | None = None
    observation_metadata: ObservationMetadata = field(default_factory=ObservationMetadata)

    # Provisional fields documented for team review (D1 / D3 agreement)
    provisional_redirect_chain: list[str] = field(default_factory=list)
    provisional_response_headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class CrawlManifest:
    """Summary manifest of discovered, selected, skipped, and failed URLs."""

    base_url: str
    total_discovered: int = 0
    discovered_urls: list[str] = field(default_factory=list)
    selected_urls: list[str] = field(default_factory=list)
    skipped_urls: list[dict[str, str]] = field(default_factory=list)  # [{"url": ..., "reason": ...}]
    failed_urls: list[dict[str, str]] = field(default_factory=list)   # [{"url": ..., "error": ...}]
    crawl_start_time: str = ""
    crawl_end_time: str = ""


@dataclass(frozen=True)
class CrawlBundle:
    """Comprehensive crawl result bundle containing page records and crawl manifest.

    Guaranteed to have zero dependencies on Playwright classes.
    """

    base_url: str
    records: list[CrawlRecord] = field(default_factory=list)
    manifest: CrawlManifest | None = None
    crawler_user_agent: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize CrawlBundle to a plain JSON-serializable Python dictionary."""
        def serialize_value(v: Any) -> Any:
            if isinstance(v, Enum):
                return v.value
            if hasattr(v, "__dataclass_fields__"):
                return {k: serialize_value(getattr(v, k)) for k in v.__dataclass_fields__}
            if isinstance(v, list):
                return [serialize_value(item) for item in v]
            if isinstance(v, dict):
                return {k: serialize_value(val) for k, val in v.items()}
            return v

        return serialize_value(self)

    def to_json(self, indent: int | None = 2) -> str:
        """Serialize CrawlBundle to deterministic JSON string with preserved record order."""
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CrawlBundle":
        """Reconstruct CrawlBundle from a dictionary with strict validation."""
        if not isinstance(data, dict):
            raise ValueError("Expected dictionary for CrawlBundle deserialization")

        if "base_url" not in data or not data["base_url"]:
            raise ValueError("Missing required field 'base_url' in CrawlBundle")

        manifest_data = data.get("manifest")
        manifest = None
        if manifest_data:
            if not isinstance(manifest_data, dict):
                raise ValueError("Manifest data must be a dictionary")
            manifest = CrawlManifest(
                base_url=manifest_data.get("base_url", ""),
                total_discovered=manifest_data.get("total_discovered", 0),
                discovered_urls=manifest_data.get("discovered_urls", []),
                selected_urls=manifest_data.get("selected_urls", []),
                skipped_urls=manifest_data.get("skipped_urls", []),
                failed_urls=manifest_data.get("failed_urls", []),
                crawl_start_time=manifest_data.get("crawl_start_time", ""),
                crawl_end_time=manifest_data.get("crawl_end_time", ""),
            )

        records = []
        for idx, r in enumerate(data.get("records", [])):
            if not isinstance(r, dict):
                raise ValueError(f"Record at index {idx} must be a dictionary")

            # Validate required fields
            for req in ("canonical_url", "source_url", "page_type", "access_state", "fetch_timestamp"):
                if req not in r or r[req] is None or r[req] == "":
                    raise ValueError(f"Record at index {idx} missing required field '{req}'")

            obs_data = r.get("observation_metadata", {})
            if not isinstance(obs_data, dict):
                obs_data = {}

            # Handle both boolean (from legacy/simple dictionaries) and TriState strings
            def parse_tristate(val: Any) -> TriState:
                if isinstance(val, TriState):
                    return val
                if isinstance(val, str):
                    try:
                        return TriState(val)
                    except ValueError:
                        pass
                if val is True:
                    return TriState.OBSERVED
                if val is False:
                    return TriState.NOT_OBSERVED
                return TriState.UNKNOWN

            # Fallback for old boolean keys if present
            nl = obs_data.get("newsletter_form", obs_data.get("has_newsletter_form", TriState.NOT_OBSERVED))
            em = obs_data.get("email_input", obs_data.get("has_email_input", TriState.NOT_OBSERVED))
            ph = obs_data.get("phone_input", obs_data.get("has_phone_input", TriState.NOT_OBSERVED))
            pop = obs_data.get("promotional_popup", obs_data.get("has_promotional_popup", TriState.NOT_OBSERVED))
            dia = obs_data.get("dialog_modal", obs_data.get("has_dialog_modal", TriState.NOT_OBSERVED))
            ck = obs_data.get("cookie_banner", obs_data.get("has_cookie_banner", TriState.NOT_OBSERVED))

            obs = ObservationMetadata(
                newsletter_form=parse_tristate(nl),
                email_input=parse_tristate(em),
                phone_input=parse_tristate(ph),
                promotional_popup=parse_tristate(pop),
                dialog_modal=parse_tristate(dia),
                cookie_banner=parse_tristate(ck),
                observed_form_actions=obs_data.get("observed_form_actions", []),
                observed_input_labels=obs_data.get("observed_input_labels", []),
                extra_signals=obs_data.get("extra_signals", {}),
            )

            try:
                page_type_enum = PageType(r["page_type"])
            except ValueError:
                raise ValueError(f"Invalid page_type: {r['page_type']}")

            try:
                access_state_enum = AccessState(r["access_state"])
            except ValueError:
                raise ValueError(f"Invalid access_state: {r['access_state']}")

            record = CrawlRecord(
                canonical_url=r["canonical_url"],
                source_url=r["source_url"],
                page_type=page_type_enum,
                http_status=r.get("http_status"),
                content_type=r.get("content_type"),
                access_state=access_state_enum,
                fetch_timestamp=r["fetch_timestamp"],
                rendered_html=r.get("rendered_html", ""),
                visible_text=r.get("visible_text", ""),
                script_urls=r.get("script_urls", []),
                access_reason=r.get("access_reason", ""),
                error_message=r.get("error_message"),
                observation_metadata=obs,
                provisional_redirect_chain=r.get("provisional_redirect_chain", []),
                provisional_response_headers=r.get("provisional_response_headers", {}),
            )
            records.append(record)

        return cls(
            base_url=data["base_url"],
            records=records,
            manifest=manifest,
            crawler_user_agent=data.get("crawler_user_agent", ""),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "CrawlBundle":
        """Deserialize CrawlBundle from JSON string with strict JSON parsing."""
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Malformed JSON: {e}") from e
        return cls.from_dict(data)
