"""URL Guard interface and Dev1 adapter boundary.

Developer 1 owns URL validation and SSRF protection.
Browser automation must fail closed when the required guard is not configured.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
import ipaddress
from typing import Any
from urllib.parse import urlparse

from browser_automation.exceptions import UrlGuardError
from browser_automation.logging import logger


@dataclass(frozen=True)
class UrlValidationResult:
    """Result of validating a target URL against Dev1 SSRF and safety rules."""

    is_safe: bool
    reason: str = ""
    normalized_url: str | None = None
    metadata: dict[str, Any] | None = None


class BaseUrlGuard(ABC):
    """Abstract interface defining the contract expected from Developer 1's URL guard."""

    @abstractmethod
    def validate_url(self, url: str) -> UrlValidationResult:
        """Validate whether a URL is safe to navigate to (preventing SSRF, internal network probing, etc.)."""
        pass


def is_private_or_local_host(hostname: str) -> bool:
    """Check if a hostname resolves to or represents a localhost, loopback, private, link-local, reserved, or unspecified address."""
    if not hostname:
        return True

    # Normalize hostname: lowercase and strip trailing dots
    norm_host = hostname.strip().rstrip(".").lower()

    if norm_host in {
        "localhost",
        "localhost.localdomain",
        "ip6-localhost",
        "ip6-loopback",
    }:
        return True

    # Handle IPv6 brackets if present in raw host
    if norm_host.startswith("[") and norm_host.endswith("]"):
        norm_host = norm_host[1:-1]

    try:
        ip = ipaddress.ip_address(norm_host)
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_unspecified
            or ip.is_multicast
        )
    except ValueError:
        pass

    return False


class FailClosedUrlGuard(BaseUrlGuard):
    """Default guard that fails closed when no Dev1 guard is injected.

    Rejects localhost, loopback, private IPs, link-local, reserved, and unspecified addresses.
    Rejection of private/local destinations is unconditional and remains active even when allow_all=True.
    Allows explicit mock/test hosts only when expressly configured and NOT resolving to a private/local address.
    """

    def __init__(self, allow_all: bool = False, allowed_hosts: set[str] | None = None):
        self._allow_all = allow_all
        self._allowed_hosts = {h.strip().rstrip(".").lower() for h in (allowed_hosts or set())}

    def validate_url(self, url: str) -> UrlValidationResult:
        if not url or not isinstance(url, str) or not url.strip():
            return UrlValidationResult(is_safe=False, reason="Invalid URL: empty or non-string input")

        try:
            parsed = urlparse(url.strip())
            if not parsed.scheme or not parsed.netloc:
                return UrlValidationResult(is_safe=False, reason="Invalid URL structure or scheme missing")

            scheme = parsed.scheme.lower()
            if scheme not in {"http", "https"}:
                return UrlValidationResult(is_safe=False, reason=f"Unsupported scheme: {parsed.scheme}")

            # Robust hostname extraction
            hostname = parsed.hostname
            if not hostname:
                return UrlValidationResult(is_safe=False, reason="Missing or invalid hostname in URL")

            norm_host = hostname.strip().rstrip(".").lower()

            # Unconditional rejection of localhost, private IPs, loopback, etc.
            # Private-address rejection must remain active even with allow_all=True
            if is_private_or_local_host(norm_host):
                return UrlValidationResult(
                    is_safe=False,
                    reason=f"Rejected destination: host '{norm_host}' is a localhost/private/link-local address (SSRF prevention)",
                )

            if self._allow_all:
                return UrlValidationResult(is_safe=True, reason="Allow-all test guard active", normalized_url=url)

            if norm_host in self._allowed_hosts:
                return UrlValidationResult(is_safe=True, reason=f"Host '{norm_host}' is explicitly allowed", normalized_url=url)

            # Fail closed for any external navigation pending Dev1 integration
            logger.warning(
                f"URL Guard failed closed for '{url}'. "
                "Developer 1 URL guard implementation is pending."
            )
            return UrlValidationResult(
                is_safe=False,
                reason="Dev1 URL Guard pending: external navigation failed closed for safety",
            )
        except Exception as e:
            return UrlValidationResult(is_safe=False, reason=f"URL parsing exception: {e}")


def assert_safe_url(guard: BaseUrlGuard | None, url: str) -> str:
    """Enforce URL guard validation, failing closed if guard is missing or rejects the URL."""
    if guard is None:
        raise UrlGuardError(
            f"Navigation failed closed: No URL Guard configured to validate '{url}'. "
            "Developer 1 SSRF guard integration required."
        )

    result = guard.validate_url(url)
    if not result.is_safe:
        raise UrlGuardError(
            f"URL Guard rejected navigation to '{url}': {result.reason}"
        )

    return result.normalized_url or url
