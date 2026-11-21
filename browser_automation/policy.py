"""Safe Crawl Policy and boundaries for browser automation."""

from dataclasses import dataclass, field
from math import isfinite
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

from browser_automation.exceptions import PolicyViolationError, RobotsDisallowedError, UrlGuardError
from browser_automation.guard import BaseUrlGuard, FailClosedUrlGuard, assert_safe_url
from browser_automation.robots import RobotsPolicy
from browser_automation.logging import logger


TRACKING_QUERY_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "gclid",
    "fbclid",
    "msclkid",
    "mc_cid",
    "mc_eid",
    "_ga",
    "_gl",
}


def normalize_url(url: str) -> str:
    """Normalize a URL: lowercase scheme & host, sort/filter tracking query parameters, remove fragments."""
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Normalize default ports
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    elif scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]

    path = parsed.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    # Strip analytics/tracking params, preserve meaningful functional parameters
    query_params = parse_qsl(parsed.query, keep_blank_values=True)
    filtered_params = [
        (k, v) for k, v in query_params if k.lower() not in TRACKING_QUERY_PARAMS
    ]
    filtered_params.sort(key=lambda x: x[0])
    query = urlencode(filtered_params)

    return urlunparse((scheme, netloc, path, "", query, ""))


def get_origin(url: str) -> str:
    """Extract normalized origin (scheme://host:port) from a URL."""
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    elif scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]
    return f"{scheme}://{netloc}"


@dataclass(frozen=True)
class CrawlPolicy:
    """Configurable crawling policy governing boundaries, limits, and polite behavior."""

    # Crawler identity
    user_agent: str = "DLitheEcommerceBot/1.0 (+https://github.com/dlithe/ecommerce-research)"

    # Polite delay between page requests (seconds)
    polite_delay_seconds: float = 1.0

    # Navigation timeouts and limits
    page_timeout_seconds: float = 30.0
    max_total_duration_seconds: float = 180.0
    post_load_settle_seconds: float = 0.25
    max_pages: int = 7
    max_redirects: int = 5
    max_response_size_bytes: int = 5 * 1024 * 1024  # 5 MB
    max_scroll_attempts: int = 2

    # Robots.txt policy
    respect_robots_txt: bool = True
    fail_closed_on_robots_error: bool = True

    # Same-site enforcement
    same_site_only: bool = True

    def __post_init__(self):
        """Validate configuration values rejecting negative/invalid limits at construction time."""
        if self.polite_delay_seconds < 0:
            raise ValueError(f"polite_delay_seconds must be non-negative, got {self.polite_delay_seconds}")
        if self.page_timeout_seconds <= 0:
            raise ValueError(f"page_timeout_seconds must be positive, got {self.page_timeout_seconds}")
        if self.max_total_duration_seconds <= 0:
            raise ValueError(f"max_total_duration_seconds must be positive, got {self.max_total_duration_seconds}")
        if not isfinite(self.post_load_settle_seconds) or self.post_load_settle_seconds < 0:
            raise ValueError(
                f"post_load_settle_seconds must be finite and non-negative, got {self.post_load_settle_seconds}"
            )
        if self.post_load_settle_seconds > 2.0:
            object.__setattr__(self, "post_load_settle_seconds", 2.0)
        if self.max_pages < 1:
            raise ValueError(f"max_pages must be at least 1, got {self.max_pages}")
        if self.max_redirects < 0:
            raise ValueError(f"max_redirects must be non-negative, got {self.max_redirects}")
        if self.max_response_size_bytes < 1024:
            raise ValueError(f"max_response_size_bytes must be at least 1024 bytes, got {self.max_response_size_bytes}")
        if self.max_scroll_attempts < 0:
            raise ValueError(f"max_scroll_attempts must be non-negative, got {self.max_scroll_attempts}")
        if self.max_scroll_attempts > 2:
            # Enforce hard maximum of two scroll attempts
            object.__setattr__(self, "max_scroll_attempts", 2)

    def validate_ssrf(self, target_url: str, url_guard: BaseUrlGuard | None) -> str:
        """Validate that target_url passes SSRF and destination safety checks.

        This check applies to ALL outbound requests (navigations, scripts, stylesheets,
        images, fonts, XHR/fetch, subresources). It rejects private IPs, loopback,
        localhost, and unvetted destinations, failing closed if guard is missing.
        """
        return assert_safe_url(url_guard, target_url)

    def validate_same_site(self, base_origin: str, target_url: str) -> bool:
        """Check if target_url belongs to the same origin as base_origin."""
        target_origin = get_origin(target_url)
        return base_origin.lower() == target_origin.lower()

    def enforce_navigation_policy(
        self,
        target_url: str,
        base_origin: str | None = None,
        url_guard: BaseUrlGuard | None = None,
        robots_policy: RobotsPolicy | None = None,
    ) -> str:
        """Validate target_url for main-frame document navigation.

        Enforces:
        1. SSRF Guard validation (Dev1 SSRF protection boundary) - Fail Closed
        2. Same-site restriction (against base_origin)
        3. Robots.txt evaluation (against robots_policy)

        Returns normalized target URL if valid.
        Raises PolicyViolationError or subclass if rejected.
        """
        # 1. URL Guard validation (Dev1 SSRF protection boundary)
        validated_url = self.validate_ssrf(target_url, url_guard)
        normalized = normalize_url(validated_url)

        # 2. Same-site restriction for navigation
        if self.same_site_only and base_origin:
            if not self.validate_same_site(base_origin, normalized):
                raise PolicyViolationError(
                    f"Navigation rejected: Target URL '{normalized}' violates same-site policy for base origin '{base_origin}'"
                )

        # 3. Robots.txt evaluation
        if self.respect_robots_txt and robots_policy:
            allowed, reason = robots_policy.is_allowed(normalized)
            if not allowed:
                raise RobotsDisallowedError(
                    f"Robots.txt disallowed crawling '{normalized}': {reason}"
                )

        return normalized
