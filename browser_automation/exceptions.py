"""Exceptions for the browser automation module."""


class BrowserAutomationError(Exception):
    """Base exception for all browser automation errors."""
    pass


class PolicyViolationError(BrowserAutomationError):
    """Raised when navigation or operation violates crawl policy."""
    pass


class UrlGuardError(PolicyViolationError):
    """Raised when URL guard validation fails or is missing."""
    pass


class RobotsDisallowedError(PolicyViolationError):
    """Raised when robots.txt disallows crawling the URL."""
    pass


class ResourceLimitExceededError(BrowserAutomationError):
    """Raised when crawl time, page budget, or response size limit is exceeded."""
    pass


class AccessBlockedError(BrowserAutomationError):
    """Raised when access is permanently blocked (CAPTCHA, bot wall, 403, 429)."""
    pass


class PageInspectionError(BrowserAutomationError):
    """Raised when dynamic DOM inspection fails unexpectedly."""
    pass


class UnsupportedContentTypeError(PolicyViolationError):
    """Raised when navigation target or response has an unsupported content type (e.g. binary, PDF, JSON)."""
    pass


class NavigationSecurityError(PolicyViolationError):
    """Raised when unsafe redirect, SSRF, or forbidden network target is detected."""
    pass
