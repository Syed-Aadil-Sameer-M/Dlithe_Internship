from dataclasses import dataclass


@dataclass(frozen=True)
class BrowserLaunchConfig:
    """Configuration for launching the browser process."""

    headless: bool = True
    slow_mo_ms: int = 0


@dataclass(frozen=True)
class BrowserContextConfig:
    """Configuration for an isolated browser session."""

    viewport_width: int = 1366
    viewport_height: int = 768
    locale: str = "en-US"
    ignore_https_errors: bool = False
    navigation_timeout_ms: int = 30_000
    default_timeout_ms: int = 10_000
    user_agent: str | None = None
