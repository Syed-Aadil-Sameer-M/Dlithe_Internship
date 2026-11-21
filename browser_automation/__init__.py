"""Canonical exports for browser_automation package."""

from browser_automation.config import BrowserLaunchConfig, BrowserContextConfig
from browser_automation.factory import BrowserFactory
from browser_automation.policy import CrawlPolicy, normalize_url, get_origin
from browser_automation.bundle import (
    CrawlBundle,
    CrawlRecord,
    CrawlManifest,
    PageType,
    AccessState,
    ObservationMetadata,
)
from browser_automation.guard import (
    BaseUrlGuard,
    FailClosedUrlGuard,
    UrlValidationResult,
    assert_safe_url,
)
from browser_automation.robots import RobotsPolicy
from browser_automation.classifier import classify_access_state
from browser_automation.discovery import discover_and_select_pages, classify_page_type
from browser_automation.inspector import inspect_page_dom
from browser_automation.crawler import SafeCrawler
from browser_automation.exceptions import (
    BrowserAutomationError,
    PolicyViolationError,
    UrlGuardError,
    RobotsDisallowedError,
    ResourceLimitExceededError,
    AccessBlockedError,
    PageInspectionError,
)

__all__ = [
    "BrowserLaunchConfig",
    "BrowserContextConfig",
    "BrowserFactory",
    "CrawlPolicy",
    "normalize_url",
    "get_origin",
    "CrawlBundle",
    "CrawlRecord",
    "CrawlManifest",
    "PageType",
    "AccessState",
    "ObservationMetadata",
    "BaseUrlGuard",
    "FailClosedUrlGuard",
    "UrlValidationResult",
    "assert_safe_url",
    "RobotsPolicy",
    "classify_access_state",
    "discover_and_select_pages",
    "classify_page_type",
    "inspect_page_dom",
    "SafeCrawler",
    "BrowserAutomationError",
    "PolicyViolationError",
    "UrlGuardError",
    "RobotsDisallowedError",
    "ResourceLimitExceededError",
    "AccessBlockedError",
    "PageInspectionError",
]
