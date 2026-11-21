"""Dynamic DOM inspection on publicly rendered DOM.

Inspects newsletter forms, email/phone inputs, dialogs, modals, popups, and script URLs.
Enforces strict visibility, non-invasive observation:
- Never submits forms.
- Never collects entered input values.
- Never clicks accept, reject, close or dismiss controls.
- Hard maximum of 2 scroll attempts.
- Distinguishes OBSERVED, NOT_OBSERVED, and UNKNOWN via TriState.
"""

from dataclasses import replace
import re
from typing import Any
from playwright.async_api import Page

from browser_automation.bundle import ObservationMetadata, TriState
from browser_automation.logging import logger


NEWSLETTER_FORM_KEYWORDS = re.compile(
    r"newsletter|subscribe|sign up for updates|mailing list|get updates|join our club|stay in touch",
    re.I,
)
PHONE_FIELD_KEYWORDS = re.compile(r"phone|mobile|sms", re.I)
PROMOTION_KEYWORDS = re.compile(
    r"\b(?:sale|discount|offer|deal|promo|newsletter|subscribe)\b|\boff\b",
    re.I,
)

OBSERVATION_FIELDS = (
    "newsletter_form",
    "email_input",
    "phone_input",
    "promotional_popup",
    "dialog_modal",
    "cookie_banner",
)


async def _is_visible(element: Any) -> bool:
    """Check if an element is genuinely visible to the user."""
    try:
        return await element.is_visible()
    except Exception:
        return False


async def _inspect_dynamic_signals(page: Page) -> ObservationMetadata:
    # State containers
    has_email = False
    has_phone = False
    has_newsletter = False
    has_dialog = False
    has_popup = False
    has_cookie = False

    observed_labels: list[str] = []
    observed_actions: list[str] = []

    try:
        # 1. Email and Phone inputs: MUST be visible
        inputs = await page.query_selector_all("input")
        for inp in inputs:
            if not await _is_visible(inp):
                continue

            inp_type = (await inp.get_attribute("type") or "text").lower()
            name = (await inp.get_attribute("name") or "").lower()
            placeholder = (await inp.get_attribute("placeholder") or "").lower()
            aria_label = (await inp.get_attribute("aria-label") or "").lower()
            label_text = await inp.evaluate(
                "(element) => Array.from(element.labels || []).map((label) => label.innerText).join(' ')"
            )
            input_context = f"{name} {placeholder} {aria_label} {label_text}".lower()

            # Email check
            if inp_type == "email" or "email" in input_context:
                has_email = True

            # Phone check
            if inp_type == "tel" or PHONE_FIELD_KEYWORDS.search(input_context):
                has_phone = True

        # 2. Forms: Check visible forms with inputs for newsletter context
        forms = await page.query_selector_all("form")
        for form in forms:
            if not await _is_visible(form):
                continue

            action = await form.get_attribute("action")
            if action:
                observed_actions.append(action.strip())

            form_text = await form.inner_text()
            form_context = [form_text, action or ""]
            for attribute in ("aria-label", "name", "id", "class"):
                value = await form.get_attribute(attribute)
                if value:
                    form_context.append(value)

            if NEWSLETTER_FORM_KEYWORDS.search(" ".join(form_context)):
                # Verify it has an input
                form_inputs = await form.query_selector_all("input")
                has_form_input = False
                for fi in form_inputs:
                    if await _is_visible(fi):
                        has_form_input = True
                        break
                if has_form_input:
                    has_newsletter = True

        # 3. Sample visible labels (read-only label text, NEVER reading entered input values)
        labels = await page.query_selector_all("label")
        for lbl in labels:
            if not await _is_visible(lbl):
                continue
            text = (await lbl.inner_text()).strip()
            if text and text[:60] not in observed_labels:
                observed_labels.append(text[:60])
            if len(observed_labels) >= 20:
                break

        # Prefer dialog semantics; use class selectors only as a fallback.
        dialog_elements = await page.query_selector_all(
            "dialog, [role='dialog'], [role='alertdialog'], [aria-modal='true']"
        )
        for dlg in dialog_elements:
            if await _is_visible(dlg):
                has_dialog = True
                dlg_text = await dlg.inner_text()
                dlg_label = await dlg.get_attribute("aria-label") or ""
                if PROMOTION_KEYWORDS.search(f"{dlg_text} {dlg_label}"):
                    has_popup = True
        fallback_dialogs = await page.query_selector_all(".modal, .popup")
        for dlg in fallback_dialogs:
            if await _is_visible(dlg):
                if not has_dialog:
                    has_dialog = True
                dlg_text = await dlg.inner_text()
                dlg_label = await dlg.get_attribute("aria-label") or ""
                if PROMOTION_KEYWORDS.search(f"{dlg_text} {dlg_label}"):
                    has_popup = True

        # Semantic labels take precedence over fragile class and ID conventions.
        semantic_promos = await page.query_selector_all(
            "[aria-label*='discount' i], [aria-label*='offer' i], [aria-label*='promo' i]"
        )
        for pop in semantic_promos:
            if await _is_visible(pop):
                has_popup = True
                break
        if not has_popup:
            popup_elements = await page.query_selector_all(
                ".popup, [class*='popup' i], [class*='promo' i], "
                "[id*='popup' i], [id*='promo' i]"
            )
            for pop in popup_elements:
                if await _is_visible(pop):
                    has_popup = True
                    break

        # 5. Cookie / Consent banner detection (DO NOT click accept/reject/dismiss)
        cookie_elements = await page.query_selector_all("[id*='cookie' i], [class*='cookie' i], [id*='consent' i], [class*='consent' i], [aria-label*='cookie' i], [aria-label*='consent' i]")
        for ce in cookie_elements:
            if await _is_visible(ce):
                has_cookie = True
                break

    except Exception as e:
        logger.warning(f"Error during dynamic DOM inspection: {e}")
        return ObservationMetadata(
            newsletter_form=TriState.UNKNOWN,
            email_input=TriState.UNKNOWN,
            phone_input=TriState.UNKNOWN,
            promotional_popup=TriState.UNKNOWN,
            dialog_modal=TriState.UNKNOWN,
            cookie_banner=TriState.UNKNOWN,
            observed_form_actions=[],
            observed_input_labels=[],
            extra_signals={"inspection_error": str(e)},
        )

    return ObservationMetadata(
        newsletter_form=TriState.OBSERVED if has_newsletter else TriState.NOT_OBSERVED,
        email_input=TriState.OBSERVED if has_email else TriState.NOT_OBSERVED,
        phone_input=TriState.OBSERVED if has_phone else TriState.NOT_OBSERVED,
        promotional_popup=TriState.OBSERVED if has_popup else TriState.NOT_OBSERVED,
        dialog_modal=TriState.OBSERVED if has_dialog else TriState.NOT_OBSERVED,
        cookie_banner=TriState.OBSERVED if has_cookie else TriState.NOT_OBSERVED,
        observed_form_actions=sorted(list(set(observed_actions)))[:10],
        observed_input_labels=observed_labels[:20],
        extra_signals={},
    )


def _scroll_observation_states(
    initial: ObservationMetadata,
    final: ObservationMetadata,
    window_complete: bool,
) -> dict[str, str]:
    states: dict[str, str] = {}
    for field in OBSERVATION_FIELDS:
        before = getattr(initial, field)
        after = getattr(final, field)
        if before == TriState.OBSERVED:
            states[field] = "observed_before_scroll"
        elif after == TriState.OBSERVED and before == TriState.NOT_OBSERVED:
            states[field] = "observed_after_scroll"
        elif after == TriState.OBSERVED:
            states[field] = "observed_during_window"
        elif before == TriState.UNKNOWN or after == TriState.UNKNOWN:
            states[field] = "unknown"
        elif not window_complete:
            states[field] = "unknown"
        else:
            states[field] = "not_observed_within_window"
    return states


async def inspect_page_dom(
    page: Page, max_scroll_attempts: int = 2
) -> tuple[ObservationMetadata, list[str]]:
    """Inspect visible DOM signals before and after bounded scrolling.

    Returns the final observations, per-signal timing states, and script URLs.
    """
    scroll_attempts = min(max(0, max_scroll_attempts), 2)
    script_urls: list[str] = []

    try:
        script_elements = await page.query_selector_all("script[src]")
        for elem in script_elements:
            try:
                src = await elem.get_attribute("src")
                if src and src.strip():
                    script_urls.append(src.strip())
            except Exception:
                pass
    except Exception as e:
        logger.debug(f"Non-fatal error reading script URLs: {e}")

    initial_observation = await _inspect_dynamic_signals(page)
    performed_scrolls = 0
    completed_rechecks = 0
    for attempt in range(scroll_attempts):
        try:
            await page.evaluate("window.scrollBy(0, window.innerHeight * 0.75);")
            performed_scrolls += 1
            await page.wait_for_timeout(250)
            completed_rechecks += 1
        except Exception as e:
            logger.debug(f"Scroll attempt {attempt + 1} failed: {e}")
            break

    final_observation = await _inspect_dynamic_signals(page)
    return (
        replace(
            final_observation,
            extra_signals={
                **final_observation.extra_signals,
                "scroll_observation": {
                    "scroll_attempts": performed_scrolls,
                    "rechecks_completed": completed_rechecks,
                    "recheck_delay_ms": 250,
                    "window_complete": completed_rechecks == scroll_attempts,
                    "signals": _scroll_observation_states(
                        initial_observation,
                        final_observation,
                        completed_rechecks == scroll_attempts,
                    ),
                },
            },
        ),
        sorted(set(script_urls)),
    )
