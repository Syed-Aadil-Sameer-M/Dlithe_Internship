
@'
import asyncio
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from browser_automation import (
    BrowserFactory,
    BrowserLaunchConfig,
    BrowserContextConfig,
    CrawlPolicy,
    FailClosedUrlGuard,
    SafeCrawler,
)


def validate_input_url(raw_url: str) -> tuple[str, str]:
    """Validate the demo target and extract its exact hostname."""
    url = raw_url.strip()

    parsed = urlparse(url)

    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("URL must begin with http:// or https://")

    if not parsed.hostname:
        raise ValueError("The URL must contain a valid hostname.")

    if parsed.username or parsed.password:
        raise ValueError("URLs containing embedded credentials are not permitted.")

    # Validate the port syntax if one is provided.
    _ = parsed.port

    hostname = parsed.hostname.lower().rstrip(".")

    return url, hostname


async def run_demo():
    print("\n" + "=" * 65)
    print("          DLITHE E-COMMERCE RESEARCH TOOL")
    print("             BROWSER AUTOMATION DEMO")
    print("=" * 65)

    raw_url = input("\nEnter a public e-commerce store URL: ")

    try:
        target_url, hostname = validate_input_url(raw_url)
    except ValueError as exc:
        print(f"\nInvalid URL: {exc}")
        return

    # Explicitly restrict the crawler to the entered hostname.
    url_guard = FailClosedUrlGuard(
        allowed_hosts={hostname}
    )

    # Conservative demo limits.
    policy = CrawlPolicy(
        polite_delay_seconds=1.0,
        page_timeout_seconds=20.0,
        max_total_duration_seconds=90.0,
        max_pages=5,
        max_redirects=5,
        respect_robots_txt=True,
        fail_closed_on_robots_error=True,
        same_site_only=True,
    )

    # Launch a real, visible Chromium browser.
    factory = BrowserFactory(
        launch_config=BrowserLaunchConfig(
            headless=False,
            slow_mo_ms=150,
        ),
        context_config=BrowserContextConfig(
            user_agent=policy.user_agent,
            navigation_timeout_ms=20_000,
            default_timeout_ms=10_000,
        ),
    )

    crawler = SafeCrawler(
        policy=policy,
        url_guard=url_guard,
        factory=factory,
    )

    print("\n[1/4] Configuration")
    print(f"Target URL     : {target_url}")
    print(f"Allowed host   : {hostname}")
    print(f"Maximum pages  : {policy.max_pages}")
    print(f"Total time     : {policy.max_total_duration_seconds}s")
    print("Robots policy  : Respect robots.txt")
    print("Browser        : Visible Chromium")

    print("\n[2/4] Starting crawl...")
    print("Chromium will open. The crawler will inspect permitted pages.")

    bundle = await crawler.crawl_site(target_url)

    print("\n[3/4] Crawl completed.")
    print(f"Pages captured : {len(bundle.records)}")

    for index, record in enumerate(bundle.records, start=1):
        print("\n" + "-" * 55)
        print(f"PAGE {index}")
        print(f"URL          : {record.canonical_url}")
        print(f"Page type    : {record.page_type.value}")
        print(f"HTTP status  : {record.http_status}")
        print(f"Access state : {record.access_state.value}")
        print(f"Content type : {record.content_type}")
        print(f"Visible text : {len(record.visible_text)} characters")

        preview = " ".join(record.visible_text.split())[:250]
        if preview:
            print(f"Text preview : {preview}")

    manifest = bundle.manifest

    if manifest:
        print("\n" + "=" * 55)
        print("CRAWL MANIFEST")
        print("=" * 55)
        print(f"Discovered URLs : {manifest.total_discovered}")
        print(f"Selected URLs   : {len(manifest.selected_urls)}")
        print(f"Skipped URLs    : {len(manifest.skipped_urls)}")
        print(f"Failed URLs     : {len(manifest.failed_urls)}")

        for item in manifest.skipped_urls:
            print(f"\nSkipped: {item['url']}")
            print(f"Reason : {item['reason']}")

        for item in manifest.failed_urls:
            print(f"\nFailed : {item['url']}")
            print(f"Reason : {item['error']}")

    print("\n[4/4] Saving CrawlBundle...")

    output_dir = Path("demo_output")
    output_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"crawl_result_{timestamp}.json"

    output_file.write_text(
        bundle.to_json(indent=2),
        encoding="utf-8",
    )

    print(f"\nSaved JSON: {output_file.resolve()}")
    print("\nDEMO FINISHED.")
    print("=" * 65)


if __name__ == "__main__":
    try:
        asyncio.run(run_demo())
    except KeyboardInterrupt:
        print("\nDemo interrupted by user.")
'@ | Set-Content -Encoding UTF8 .\demo.py
