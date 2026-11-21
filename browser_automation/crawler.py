"""Safe Crawler orchestrator coordinating BrowserFactory, CrawlPolicy, and CrawlBundle generation."""

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import time
from typing import Any
from urllib.parse import urljoin, urlparse

from browser_automation.bundle import (
    CrawlBundle,
    CrawlRecord,
    CrawlManifest,
    PageType,
    AccessState,
    ObservationMetadata,
    TriState,
)
from browser_automation.classifier import classify_access_state
from browser_automation.discovery import discover_and_select_pages, classify_page_type
from browser_automation.exceptions import (
    PolicyViolationError,
    UrlGuardError,
    RobotsDisallowedError,
    ResourceLimitExceededError,
    UnsupportedContentTypeError,
    NavigationSecurityError,
)
from browser_automation.factory import BrowserFactory
from browser_automation.guard import BaseUrlGuard, FailClosedUrlGuard
from browser_automation.inspector import inspect_page_dom
from browser_automation.logging import logger
from browser_automation.policy import CrawlPolicy, get_origin, normalize_url
from browser_automation.robots import RobotsPolicy
from browser_automation.config import BrowserContextConfig, BrowserLaunchConfig


ALLOWED_MEDIA_TYPES = {
    "text/html",
    "application/xhtml+xml",
}


def parse_and_validate_media_type(raw_content_type: str | None) -> tuple[bool, str]:
    """Parse HTTP Content-Type header and strictly validate media type.

    Returns (is_valid, media_type).
    Only 'text/html' and 'application/xhtml+xml' are permitted.
    """
    if not raw_content_type or not raw_content_type.strip():
        return False, "missing"

    # Extract base media type before ';' (parameters like charset)
    media_type = raw_content_type.split(";")[0].strip().lower()
    return media_type in ALLOWED_MEDIA_TYPES, media_type


class SafeCrawler:
    """Safe crawler orchestrating deterministic navigation, policy enforcement, and bundle production."""

    def __init__(
        self,
        policy: CrawlPolicy | None = None,
        url_guard: BaseUrlGuard | None = None,
        factory: BrowserFactory | None = None,
    ):
        self.policy = policy or CrawlPolicy()
        self.url_guard = url_guard or FailClosedUrlGuard()

        # If factory not provided, configure it with the policy's user_agent and timeouts
        if factory is None:
            ctx_config = BrowserContextConfig(
                user_agent=self.policy.user_agent,
                navigation_timeout_ms=int(self.policy.page_timeout_seconds * 1000),
            )
            self.factory = BrowserFactory(context_config=ctx_config)
        else:
            self.factory = factory
            # Ensure user-agent is synchronized if context_config exists
            if hasattr(self.factory, "context_config") and not self.factory.context_config.user_agent:
                object.__setattr__(self.factory.context_config, "user_agent", self.policy.user_agent)

        self.robots_policy = RobotsPolicy(
            user_agent=self.policy.user_agent,
            fail_closed_on_error=self.policy.fail_closed_on_robots_error,
        )

    async def fetch_robots_txt(self, base_url: str, total_deadline: float) -> None:
        """Fetch and parse robots.txt for the site if enabled, within remaining budget."""
        if not self.policy.respect_robots_txt:
            return

        robots_url = RobotsPolicy.get_robots_url(base_url)
        origin = get_origin(base_url)

        try:
            # 1. Validate initial robots.txt URL with SSRF Guard and same-origin check
            self.policy.enforce_navigation_policy(
                target_url=robots_url,
                base_origin=origin,
                url_guard=self.url_guard,
                robots_policy=None,  # Do not check robots rules on robots.txt itself
            )

            page = self.factory.page
            if page is None:
                raise RuntimeError("Browser page not ready for robots.txt fetch")

            request_context = page.request
            current_url = robots_url
            redirect_count = 0

            while True:
                remaining_budget = total_deadline - time.monotonic()
                if remaining_budget <= 0:
                    self.robots_policy.record_fetch_failure(
                        origin, "Crawl deadline expired during robots fetch"
                    )
                    return

                timeout_ms = int(min(self.policy.page_timeout_seconds, remaining_budget) * 1000)
                if timeout_ms <= 0:
                    self.robots_policy.record_fetch_failure(
                        origin, "Crawl deadline expired before robots fetch"
                    )
                    return

                response = await request_context.get(
                    current_url,
                    timeout=timeout_ms,
                    max_redirects=0,
                    headers={"User-Agent": self.policy.user_agent},
                )
                try:
                    status = response.status
                    if status in (301, 302, 303, 307, 308):
                        location = response.headers.get("location")
                        if not location:
                            self.robots_policy.record_fetch_failure(
                                origin, f"HTTP {status} redirect has no Location header"
                            )
                            return
                        if redirect_count >= self.policy.max_redirects:
                            self.robots_policy.record_fetch_failure(
                                origin,
                                f"Robots.txt exceeded max redirects ({self.policy.max_redirects})",
                            )
                            return

                        current_url = urljoin(current_url, location)
                        self.policy.enforce_navigation_policy(
                            target_url=current_url,
                            base_origin=origin,
                            url_guard=self.url_guard,
                            robots_policy=None,
                        )
                        redirect_count += 1
                        continue

                    if status == 200:
                        content_len_hdr = response.headers.get("content-length")
                        if content_len_hdr:
                            try:
                                if int(content_len_hdr) > self.policy.max_response_size_bytes:
                                    self.robots_policy.record_fetch_failure(
                                        origin,
                                        f"Robots.txt Content-Length ({content_len_hdr} bytes) exceeded limit",
                                    )
                                    return
                            except ValueError:
                                pass

                        raw_body = await response.body()
                        if len(raw_body) > self.policy.max_response_size_bytes:
                            self.robots_policy.record_fetch_failure(
                                origin,
                                f"Robots.txt body size ({len(raw_body)} bytes) exceeded limit",
                            )
                            return

                        self.robots_policy.parse_robots_txt_content(
                            origin, raw_body.decode("utf-8", errors="replace")
                        )
                    elif status in (404, 410):
                        self.robots_policy.parse_robots_txt_content(origin, "")
                    elif status in (401, 403, 429):
                        self.robots_policy.record_fetch_failure(
                            origin, f"HTTP Access Denied/Throttled: {status}"
                        )
                    else:
                        self.robots_policy.record_fetch_failure(origin, f"HTTP {status}")
                    return
                finally:
                    await response.dispose()

        except Exception as e:
            self.robots_policy.record_fetch_failure(origin, str(e))

    async def crawl_site(self, base_url: str) -> CrawlBundle:
        """Orchestrate safe crawling of the target store wrapped by asyncio timeout enforcing total deadline."""
        start_time = datetime.now(timezone.utc).isoformat()
        start_clock = time.monotonic()
        total_deadline = start_clock + self.policy.max_total_duration_seconds
        base_origin = get_origin(base_url)

        records: list[CrawlRecord] = []
        skipped_urls: list[dict[str, str]] = []
        failed_urls: list[dict[str, str]] = []
        all_discovered: list[str] = [normalize_url(base_url)]
        selected_urls_manifest: list[str] = []

        try:
            # Wrap the entire crawl execution in asyncio.timeout
            async with asyncio.timeout(self.policy.max_total_duration_seconds):
                async with self.factory:
                    await self.factory.create_context()
                    page = await self.factory.create_page()

                    # 1. Fetch robots.txt with deadline check
                    if time.monotonic() >= total_deadline:
                        failed_urls.append({"url": base_url, "error": "Total crawl deadline expired before robots fetch"})
                        return self._build_bundle(base_url, start_time, records, all_discovered, selected_urls_manifest, skipped_urls, failed_urls)

                    await self.fetch_robots_txt(base_url, total_deadline)

                    # 2. Enforce initial policy on base_url
                    try:
                        norm_base = self.policy.enforce_navigation_policy(
                            target_url=base_url,
                            base_origin=base_origin,
                            url_guard=self.url_guard,
                            robots_policy=self.robots_policy,
                        )
                    except Exception as e:
                        failed_urls.append({"url": base_url, "error": str(e)})
                        return self._build_bundle(base_url, start_time, records, all_discovered, selected_urls_manifest, skipped_urls, failed_urls)

                    # 3. Crawl Homepage with deadline check
                    if time.monotonic() >= total_deadline:
                        failed_urls.append({"url": norm_base, "error": "Total crawl deadline expired before homepage navigation"})
                        return self._build_bundle(base_url, start_time, records, all_discovered, selected_urls_manifest, skipped_urls, failed_urls)

                    homepage_record, extracted_links = await self._crawl_single_page(
                        page=page,
                        target_url=norm_base,
                        page_type=PageType.HOMEPAGE,
                        base_origin=base_origin,
                        total_deadline=total_deadline,
                    )
                    records.append(homepage_record)
                    selected_urls_manifest.append(norm_base)

                    # If homepage failed or was blocked, update manifest
                    if homepage_record.access_state == AccessState.BLOCKED:
                        failed_urls.append({"url": norm_base, "error": f"Access blocked: {homepage_record.access_reason}"})
                    elif homepage_record.access_state == AccessState.ERROR:
                        failed_urls.append({"url": norm_base, "error": homepage_record.error_message or homepage_record.access_reason})
                    elif homepage_record.access_state == AccessState.UNAVAILABLE and homepage_record.error_message:
                        failed_urls.append({"url": norm_base, "error": homepage_record.error_message})

                    # Check if max_pages limit is reached (e.g. max_pages == 1)
                    if len(records) >= self.policy.max_pages:
                        return self._build_bundle(base_url, start_time, records, all_discovered, selected_urls_manifest, skipped_urls, failed_urls)

                    # 4. Discover and select pages from homepage links
                    selected_pages, all_discovered, skipped = discover_and_select_pages(
                        base_url=norm_base,
                        extracted_links=extracted_links,
                        max_pages=self.policy.max_pages,
                    )
                    skipped_urls.extend(skipped)

                    # 5. Crawl remaining selected pages with polite delays and hard deadline
                    for target_url, page_type in selected_pages:
                        if target_url == norm_base:
                            continue

                        # Hard deadline check
                        rem_budget = total_deadline - time.monotonic()
                        if rem_budget <= 0:
                            skipped_urls.append({
                                "url": target_url,
                                "reason": f"Total crawl deadline expired ({self.policy.max_total_duration_seconds}s limit reached)",
                            })
                            continue

                        # Max page count check
                        if len(records) >= self.policy.max_pages:
                            skipped_urls.append({
                                "url": target_url,
                                "reason": f"Maximum page count reached ({self.policy.max_pages})",
                            })
                            continue

                        # Polite delay (only if budget allows)
                        if self.policy.polite_delay_seconds > 0:
                            delay = min(self.policy.polite_delay_seconds, rem_budget)
                            if delay > 0:
                                await asyncio.sleep(delay)

                        if time.monotonic() >= total_deadline:
                            skipped_urls.append({
                                "url": target_url,
                                "reason": "Total crawl deadline expired during polite delay",
                            })
                            continue

                        # Validate against policy before navigating
                        try:
                            norm_url = self.policy.enforce_navigation_policy(
                                target_url=target_url,
                                base_origin=base_origin,
                                url_guard=self.url_guard,
                                robots_policy=self.robots_policy,
                            )
                        except Exception as e:
                            skipped_urls.append({"url": target_url, "reason": str(e)})
                            continue

                        selected_urls_manifest.append(norm_url)

                        page_record, _ = await self._crawl_single_page(
                            page=page,
                            target_url=norm_url,
                            page_type=page_type,
                            base_origin=base_origin,
                            total_deadline=total_deadline,
                        )
                        records.append(page_record)

                        if page_record.access_state == AccessState.BLOCKED:
                            failed_urls.append({"url": norm_url, "error": f"Access blocked: {page_record.access_reason}"})
                        elif page_record.access_state == AccessState.ERROR:
                            failed_urls.append({"url": norm_url, "error": page_record.error_message or page_record.access_reason})
                        elif page_record.access_state == AccessState.UNAVAILABLE and page_record.error_message:
                            failed_urls.append({"url": norm_url, "error": page_record.error_message})

        except TimeoutError:
            logger.warning(f"Crawl of {base_url} aborted: Total crawl deadline of {self.policy.max_total_duration_seconds}s expired.")
            failed_urls.append({"url": base_url, "error": f"Total crawl deadline of {self.policy.max_total_duration_seconds}s expired"})
        except Exception as e:
            logger.error(f"Unexpected error crawling {base_url}: {e}")
            failed_urls.append({"url": base_url, "error": str(e)})

        return self._build_bundle(base_url, start_time, records, all_discovered, selected_urls_manifest, skipped_urls, failed_urls)

    def _build_bundle(
        self,
        base_url: str,
        start_time: str,
        records: list[CrawlRecord],
        discovered_urls: list[str],
        selected_urls: list[str],
        skipped_urls: list[dict[str, str]],
        failed_urls: list[dict[str, str]],
    ) -> CrawlBundle:
        """Helper to construct CrawlBundle with deterministic manifest."""
        manifest = CrawlManifest(
            base_url=base_url,
            total_discovered=len(discovered_urls),
            discovered_urls=sorted(list(set(discovered_urls))),
            selected_urls=selected_urls,
            skipped_urls=skipped_urls,
            failed_urls=failed_urls,
            crawl_start_time=start_time,
            crawl_end_time=datetime.now(timezone.utc).isoformat(),
        )
        return CrawlBundle(
            base_url=base_url,
            records=records,
            manifest=manifest,
            crawler_user_agent=self.policy.user_agent,
        )

    async def _crawl_single_page(
        self,
        page: Any,
        target_url: str,
        page_type: PageType,
        base_origin: str,
        total_deadline: float,
    ) -> tuple[CrawlRecord, list[str]]:
        """Navigate to a single page with request interception, strict content-type and size validation."""
        fetch_time = datetime.now(timezone.utc).isoformat()
        http_status: int | None = None
        content_type: str | None = None
        html: str = ""
        visible_text: str = ""
        script_urls: list[str] = []
        extracted_links: list[str] = []
        observation = ObservationMetadata()
        redirect_chain: list[str] = [target_url]
        response_headers: dict[str, str] = {}
        error_msg: str | None = None

        rem_time = total_deadline - time.monotonic()
        if rem_time <= 0:
            error_msg = "Total crawl deadline expired before page navigation"
            record = CrawlRecord(
                canonical_url=normalize_url(target_url),
                source_url=target_url,
                page_type=page_type,
                http_status=None,
                content_type=None,
                access_state=AccessState.UNAVAILABLE,
                fetch_timestamp=fetch_time,
                access_reason=error_msg,
                error_message=error_msg,
            )
            return record, []

        effective_timeout = min(self.policy.page_timeout_seconds, rem_time)
        redirect_count = 0

        # Request event listener to record genuine redirects in order
        def on_request(req: Any) -> None:
            if req.is_navigation_request() and req.redirected_from is not None:
                if req.url not in redirect_chain:
                    redirect_chain.append(req.url)

        page.on("request", on_request)

        # Request interception handler: inspects EVERY outbound request
        async def handle_navigation_route(route: Any) -> None:
            nonlocal redirect_count
            req = route.request
            req_url = req.url

            # 1. SSRF Guard on ALL outbound requests (main-frame, subresources, scripts, images, etc.)
            try:
                self.policy.validate_ssrf(req_url, self.url_guard)
            except Exception as ex:
                logger.warning(f"SSRF guard aborted request to {req_url}: {ex}")
                await route.abort("blockedbyclient")
                return

            # 2. Main-frame navigation requests only:
            if req.is_navigation_request():
                # Track genuine redirects using request.redirected_from
                if req.redirected_from is not None:
                    redirect_count += 1
                    if redirect_count > self.policy.max_redirects:
                        logger.warning(f"Navigation redirect limit ({self.policy.max_redirects}) exceeded for {req_url}")
                        await route.abort("blockedbyclient")
                        return

                # Enforce same-origin and robots.txt on main-frame document navigations
                try:
                    self.policy.enforce_navigation_policy(
                        target_url=req_url,
                        base_origin=base_origin,
                        url_guard=self.url_guard,
                        robots_policy=self.robots_policy,
                    )
                except Exception as ex:
                    logger.warning(f"Main-frame navigation to {req_url} rejected: {ex}")
                    await route.abort("blockedbyclient")
                    return

            await route.fallback()

        await page.route("**/*", handle_navigation_route)

        try:
            # Enforce page navigation timeout bounded by remaining deadline
            response = await page.goto(
                target_url,
                timeout=int(effective_timeout * 1000),
                wait_until="domcontentloaded",
            )
            final_url = page.url

            if response:
                http_status = response.status
                headers = response.headers
                content_type = headers.get("content-type")
                response_headers = {k: v for k, v in list(headers.items())[:20]}

                # Strict Media-Type validation
                is_valid_type, parsed_type = parse_and_validate_media_type(content_type)
                if not is_valid_type:
                    raise UnsupportedContentTypeError(
                        f"Unsupported content-type '{content_type}' (media type: '{parsed_type}'). "
                        "Only 'text/html' and 'application/xhtml+xml' page responses permitted."
                    )

                # Response size verification (declared Content-Length)
                raw_len = headers.get("content-length")
                if raw_len:
                    try:
                        content_len = int(raw_len)
                        if content_len > self.policy.max_response_size_bytes:
                            raise ResourceLimitExceededError(
                                f"Declared Content-Length ({content_len} bytes) exceeded maximum ({self.policy.max_response_size_bytes} bytes)"
                            )
                    except ValueError:
                        logger.warning(f"Malformed Content-Length header encountered: {raw_len}")

            readiness_started = time.monotonic()
            settle_budget = total_deadline - readiness_started
            if settle_budget <= 0:
                raise TimeoutError("Total crawl deadline expired before rendered-page settling")
            settle_seconds = min(self.policy.post_load_settle_seconds, settle_budget)
            if settle_seconds:
                await asyncio.sleep(settle_seconds)
            if total_deadline - time.monotonic() <= 0:
                raise TimeoutError("Total crawl deadline expired during rendered-page settling")
            settle_elapsed_ms = round((time.monotonic() - readiness_started) * 1000)
            logger.debug(
                "Rendered-page readiness for %s: DOMContentLoaded plus %d ms settling wait",
                target_url,
                settle_elapsed_ms,
            )

            # Grab content
            html = await page.content()
            visible_text = await page.inner_text("body")

            # Check rendered HTML size against budget
            if len(html.encode("utf-8")) > self.policy.max_response_size_bytes:
                raise ResourceLimitExceededError(
                    f"Rendered HTML size ({len(html.encode('utf-8'))} bytes) exceeded maximum ({self.policy.max_response_size_bytes} bytes)"
                )

            # Check remaining budget before DOM inspection
            inspection_rem = total_deadline - time.monotonic()
            if inspection_rem <= 0:
                raise TimeoutError("Total crawl deadline expired before DOM inspection")

            # Extract outgoing links
            link_elements = await page.query_selector_all("a[href]")
            for link in link_elements:
                try:
                    href = await link.get_attribute("href")
                    if href:
                        extracted_links.append(href)
                except Exception:
                    pass

            # Dynamic DOM inspection wrapped with remaining time check
            async with asyncio.timeout(inspection_rem):
                observation, script_urls = await inspect_page_dom(
                    page=page,
                    max_scroll_attempts=self.policy.max_scroll_attempts,
                )
            observation = replace(
                observation,
                extra_signals={
                    **observation.extra_signals,
                    "page_readiness": {
                        "strategy": "domcontentloaded_bounded_settle",
                        "settle_wait_ms": settle_elapsed_ms,
                    },
                },
            )

            access_state, access_reason = classify_access_state(
                http_status=http_status,
                rendered_html=html,
                visible_text=visible_text,
                final_url=final_url,
            )

        except TimeoutError:
            error_msg = "Total crawl deadline expired during page operation or inspection"
            logger.warning(f"{error_msg} for {target_url}")
            access_state = AccessState.UNAVAILABLE
            access_reason = error_msg
            observation = ObservationMetadata(
                newsletter_form=TriState.UNKNOWN,
                email_input=TriState.UNKNOWN,
                phone_input=TriState.UNKNOWN,
                promotional_popup=TriState.UNKNOWN,
                dialog_modal=TriState.UNKNOWN,
                cookie_banner=TriState.UNKNOWN,
                extra_signals={"deadline_timeout": True},
            )
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"Error crawling {target_url}: {e}")
            access_state, access_reason = classify_access_state(
                http_status=http_status,
                rendered_html=html,
                visible_text=visible_text,
                final_url=target_url,
                error=e,
            )
            # If inspection failed due to error, metadata is marked unknown
            observation = ObservationMetadata(
                newsletter_form=TriState.UNKNOWN,
                email_input=TriState.UNKNOWN,
                phone_input=TriState.UNKNOWN,
                promotional_popup=TriState.UNKNOWN,
                dialog_modal=TriState.UNKNOWN,
                cookie_banner=TriState.UNKNOWN,
                extra_signals={"crawl_error": str(e)},
            )
        finally:
            try:
                page.remove_listener("request", on_request)
            except Exception:
                pass
            try:
                await page.unroute("**/*", handle_navigation_route)
            except Exception:
                pass

        record = CrawlRecord(
            canonical_url=normalize_url(page.url if page and hasattr(page, "url") and page.url else target_url),
            source_url=target_url,
            page_type=page_type,
            http_status=http_status,
            content_type=content_type,
            access_state=access_state,
            fetch_timestamp=fetch_time,
            rendered_html=html,
            visible_text=visible_text,
            script_urls=script_urls,
            access_reason=access_reason,
            error_message=error_msg,
            observation_metadata=observation,
            provisional_redirect_chain=redirect_chain,
            provisional_response_headers=response_headers,
        )

        return record, extracted_links
