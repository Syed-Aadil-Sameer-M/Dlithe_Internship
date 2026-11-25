"""robots.txt fetching, parsing, and User-Agent evaluation."""

import urllib.robotparser
from urllib.parse import urlparse
from typing import Any

from browser_automation.logging import logger


class RobotsPolicy:
    """Fetches, parses, and evaluates robots.txt rules for a specific origin and crawler User-Agent."""

    def __init__(
        self,
        user_agent: str,
        fail_closed_on_error: bool = True,
    ):
        self.user_agent = user_agent
        self.fail_closed_on_error = fail_closed_on_error
        self._parsers: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._errors: dict[str, str] = {}

    @staticmethod
    def get_robots_url(target_url: str) -> str:
        """Construct the robots.txt URL for a given target URL."""
        parsed = urlparse(target_url)
        return f"{parsed.scheme}://{parsed.netloc}/robots.txt"

    def parse_robots_txt_content(self, origin: str, content: str) -> None:
        """Parse raw robots.txt text content for a specified origin."""
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(f"{origin}/robots.txt")
        rp.parse(content.splitlines())
        self._parsers[origin.lower()] = rp
        logger.info(f"Loaded and parsed robots.txt for origin {origin}")

    def record_fetch_failure(self, origin: str, error_message: str) -> None:
        """Record that robots.txt retrieval failed for this origin."""
        self._parsers[origin.lower()] = None
        self._errors[origin.lower()] = error_message
        logger.warning(f"Robots.txt retrieval failed for {origin}: {error_message}")

    def is_allowed(self, url: str) -> tuple[bool, str]:
        """Check if crawling the URL is allowed for the crawler's User-Agent.

        Returns (is_allowed, reason).
        """
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return False, "Invalid URL"

        origin = f"{parsed.scheme}://{parsed.netloc}".lower()

        if origin not in self._parsers:
            if self.fail_closed_on_error:
                return False, f"Robots.txt has not been retrieved for {origin} (conservative fail-closed)"
            return True, "No robots.txt retrieved; lenient policy allowed"

        rp = self._parsers.get(origin)
        if rp is None:
            # Fetch failed earlier
            error = self._errors.get(origin, "Unknown fetch failure")
            if self.fail_closed_on_error:
                return False, f"Robots.txt retrieval failed for {origin} ({error}); fail-closed policy disallows crawling"
            return True, f"Robots.txt retrieval failed for {origin} ({error}); lenient policy permits crawling"

        # Evaluate against the user agent
        allowed = rp.can_fetch(self.user_agent, url)
        if not allowed:
            return False, f"Disallowed by robots.txt rule for User-Agent '{self.user_agent}'"

        return True, "Allowed by robots.txt"
