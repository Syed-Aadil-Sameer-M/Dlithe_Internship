# Dlithe_Internship

## Browser automation: rendered-page readiness

`SafeCrawler` waits for `DOMContentLoaded`, then applies a short bounded settling
delay before capturing rendered HTML. This gives commerce pages time to render
late product, offer, and storefront UI without waiting indefinitely for analytics
or other network activity. The selected readiness strategy and observed wait
duration are recorded in each page's `observation_metadata.extra_signals`.

Configure the delay with `CrawlPolicy(post_load_settle_seconds=0.25)`. It defaults
to 0.25 seconds, accepts zero to disable the extra wait, and is capped at two
seconds. The wait is limited by the remaining crawl deadline; deadline expiry is
reported as an unavailable page. This is a bounded capture window, not a guarantee
that a page has finished all asynchronous work.

After capture, DOM inspection compares visible signals before and after the
configured bounded scroll checks (`CrawlPolicy.max_scroll_attempts`, hard-capped
at two). Per-signal states are recorded in
`observation_metadata.extra_signals.scroll_observation.signals`, distinguishing
`observed_before_scroll`, `observed_after_scroll`,
`not_observed_within_window`, and `unknown`. “Not observed” is not proof of
absence. The same object reports performed scrolls, completed rechecks, and
whether the observation window completed. Email/phone fields and offer/dialog
markers prefer semantic labels and ARIA attributes; class and ID heuristics are
fallbacks. The crawler never reads entered input values, submits forms, or
accepts/rejects/dismisses consent. The readiness wait and DOM inspection do not
bypass the crawler's robots, URL-guard, redirect, deadline, or response-size
policies.

## Browser automation: retries and request pacing

Navigation retries are bounded by `CrawlPolicy.max_retries` (two retries by
default) and the total crawl deadline. HTTP 408, 429, and selected transient
server responses (500, 502, 503, and 504) may be retried with jittered
exponential backoff. A valid `Retry-After` value in seconds or HTTP-date format
takes precedence; waits are capped by `max_retry_delay_seconds` (30 seconds by
default). `retry_backoff_base_seconds` defaults to one second. Permanent client
errors, CAPTCHA/bot challenges, and explicit access denials are not retried.

Requests are paced per normalized origin using `polite_delay_seconds` (one
second by default). A 429 pauses further requests to that origin for the
bounded server-provided or backoff delay. Unrelated origins have independent
pacing state. Robots.txt retrieval is not retried and retains its configured
fail-closed behavior.
