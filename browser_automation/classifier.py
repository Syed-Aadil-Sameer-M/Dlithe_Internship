"""Classification of page accessibility state based on HTTP responses and visible DOM signals."""

import re
from typing import Any
from browser_automation.bundle import AccessState
from browser_automation.logging import logger


CAPTCHA_PATTERNS = [
    re.compile(r"cf-turnstile", re.I),
    re.compile(r"g-recaptcha", re.I),
    re.compile(r"h-captcha", re.I),
    re.compile(r"hcaptcha\.com", re.I),
    re.compile(r"recaptcha/api", re.I),
    re.compile(r"challenge-platform", re.I),
    re.compile(r"arkose-labs", re.I),
    re.compile(r"perimeterx", re.I),
    re.compile(r"datadome", re.I),
    re.compile(r"bot detection", re.I),
    re.compile(r"verify you are human", re.I),
    re.compile(r"access to this page has been denied", re.I),
    re.compile(r"please complete the security check", re.I),
    re.compile(r"attention required! \| cloudflare", re.I),
]

LOGIN_PATTERNS = [
    re.compile(r"/accounts?/login", re.I),
    re.compile(r"/signin", re.I),
    re.compile(r"/auth/login", re.I),
]


def classify_access_state(
    http_status: int | None,
    rendered_html: str,
    visible_text: str,
    final_url: str = "",
    error: Exception | str | None = None,
) -> tuple[AccessState, str]:
    """Classify the access state with robust evidence.

    Returns (AccessState, reason).
    """
    if error is not None:
        err_str = str(error).lower()
        if "timeout" in err_str:
            return AccessState.UNAVAILABLE, f"Navigation or render timed out: {error}"
        if "net::err" in err_str or "connection" in err_str or "cannot reach" in err_str:
            return AccessState.UNAVAILABLE, f"Network or connectivity failure: {error}"
        return AccessState.ERROR, f"Browser navigation exception: {error}"

    # HTTP Status Checks
    if http_status is not None:
        if http_status in (401, 403):
            return AccessState.BLOCKED, f"HTTP Access Denied with status code {http_status}"
        if http_status == 429:
            return AccessState.BLOCKED, "HTTP Rate Limited (Status 429)"
        if http_status in (404, 410):
            return AccessState.UNAVAILABLE, f"Page not found (HTTP {http_status})"
        if http_status >= 500:
            return AccessState.UNAVAILABLE, f"Server error response (HTTP {http_status})"

    # Content checks for Bot Wall / CAPTCHA
    combined_content = f"{visible_text} {rendered_html[:10000]}"
    for pattern in CAPTCHA_PATTERNS:
        if pattern.search(combined_content):
            return AccessState.BLOCKED, f"Bot protection or CAPTCHA detected matching pattern '{pattern.pattern}'"

    # Login requirement checks
    if any(p.search(final_url) for p in LOGIN_PATTERNS):
        return AccessState.BLOCKED, f"Redirected to login endpoint: {final_url}"

    # Empty render check
    stripped_text = visible_text.strip()
    stripped_html = rendered_html.strip()

    if not stripped_html:
        return AccessState.UNAVAILABLE, "Empty render: No HTML document returned"

    # Check for empty DOM body
    if len(stripped_text) < 10 and not any(tag in stripped_html.lower() for tag in ["<main", "<article", "<section", "<form", "<div"]):
        return AccessState.UNAVAILABLE, "Empty render: Blank DOM body without visible content"

    if http_status and http_status >= 400:
        return AccessState.ERROR, f"HTTP client error status {http_status}"

    return AccessState.ACCESSIBLE, "Page successfully rendered and publicly accessible"
