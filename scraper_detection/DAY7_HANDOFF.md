# Developer 3 (D3) — Week 1 Extraction Handoff Specification

## 1. Overview
This document defines the Developer 3 (Deterministic Scraping, Store Profile & Technology Detection) extraction and detection handoff for Week 1.

The D3 pipeline consumes crawled web pages produced by Developer 2 (D2), extracts verifiable facts and platform fingerprints without guesswork, and outputs canonical `EvidenceRecord` collections ready for Developer 4 (D4) evidence scoring and Developer 1 (D1) persistence.

---

## 2. Pipeline Entry Point
The unified entry point for Developer 3 is:

```python
from scraper_detection import extract_store_data

result = extract_store_data(crawl_bundle)
```

### Signature
`extract_store_data(crawl_bundle: Any) -> StoreExtractionResult`

The returned `StoreExtractionResult` exposes:
- `evidence_records: list[EvidenceRecord]` (flat canonical evidence collection for D1/D4)
- `platform: PlatformDetectionResult` (detected platform name, confidence, matched indicators)
- `store: ExtractedStoreDetails` (store.name, store.about_text)
- `contact_social: ExtractedContactSocial` (contact.email, contact.phone, social profiles)
- `products: list[ExtractedProduct]` (deduplicated products from JSON-LD / DOM)
- `records_analyzed: int`
- `base_url: str`
- Helper query methods: `get_evidence(field_name)`, `get_evidence_list(prefix)`, `to_dict()`

---

## 3. D3 Input Contract (Consumes D2 CrawlBundle / CrawlRecord)
D3 accepts instances of D2's `CrawlBundle` (or equivalent duck-typed objects/dictionaries). D3 consumes the following fields:

### From `CrawlBundle`:
- `base_url: str`: Target store origin URL for resolving relative links.
- `records: list[CrawlRecord]`: List of crawled page records.

### From `CrawlRecord`:
- `rendered_html: str`: Fully rendered page HTML for DOM and JSON-LD inspection.
- `source_url: str`: The URL of the page from which evidence is gathered.
- `canonical_url: str`: Fallback URL if source URL is empty.
- `page_type: PageType`: Semantic page classification (`homepage`, `collection`, `product`, `about`, `contact`, `other`).
- `access_state: AccessState`: Accessibility status (`Accessible`, `Blocked`, `Unavailable`, `Error`). If not `Accessible`, page extraction is skipped and `BLOCKED`/`UNAVAILABLE` evidence is recorded.
- `script_urls: list[str]`: External script tags discovered during crawl (used for platform fingerprint rules).
- `fetch_timestamp: str`: ISO 8601 UTC timestamp string (parsed into `datetime`).

*Zero Playwright classes or browser internals are imported by D3.*

---

## 4. D3 Output Contract (`EvidenceRecord`)
Every factual claim emitted by D3 strictly maps to `EvidenceRecord`:

```python
@dataclass
class EvidenceRecord:
    field: str              # Canonical field key (e.g. "product.title", "store.name")
    value: Any              # Observed value (str, float, None)
    status: EvidenceStatus  # Canonical observation status
    source_url: str         # Exact page URL where fact was observed
    observed_at: datetime   # UTC timestamp of observation
    method: EvidenceMethod  # Detection/extraction technique
    confidence: float       # Interpretable confidence score (0.0 <= c <= 1.0)
```

### Supported Field Keys:
- **Platform**: `technology.ecommerce_platform`
- **Store details**: `store.name`, `store.about_text`
- **Contact**: `contact.email`, `contact.phone`
- **Social profiles**: `social.instagram`, `social.facebook`, `social.youtube`, `social.twitter`, `social.linkedin`
- **Product catalog**: `product.title`, `product.url`, `product.price`, `product.currency`, `product.original_price`, `product.discount_price`, `product.description`, `product.availability`

---

## 5. Status Semantics (`EvidenceStatus`)
D3 adheres strictly to the canonical 6-status contract:

1. **`Found`**: The field or technology indicator was positively identified in public page evidence.
2. **`Not observed`**: The relevant page was inspected successfully, but no matching indicator was present. *(Never implies that a tool is definitively absent store-wide).*
3. **`Unavailable`**: The page or source element could not be accessed or parsed.
4. **`Unverified`**: Weak, ambiguous, or conflicting evidence was observed that cannot be confirmed without further signals.
5. **`Blocked`**: Access to the page was prevented (e.g. HTTP 403, Cloudflare challenge).
6. **`Error`**: An unexpected exception occurred during parsing.

---

## 6. Extraction Methods (`EvidenceMethod`)
- **`json_ld`**: Extracted directly from schema.org JSON-LD scripts (confidence = 1.0).
- **`dom`**: Extracted from visible DOM tags and attributes (confidence = 0.80 – 0.95).
- **`regex`**: Extracted via verified regular expressions from text (confidence = 0.70 – 0.85).
- **`meta`**: Extracted from HTML `<meta>` or `<title>` elements (confidence = 0.85 – 0.90).
- **`url`**: Extracted from anchor `href` links (confidence = 0.90 – 0.95).

---

## 7. Downstream Consumption & Coordination

### What Developer 4 (D4) Can Consume:
- D4 can consume `result.evidence_records` directly.
- All records provide traceable confidence, explicit statuses, and source URLs.
- D4 can evaluate coverage and calculate rule-based fit scores without fearing fabricated values.
- Unknown, blocked, and not-observed statuses remain strictly distinguishable so unobserved signals are not unfairly penalized as negative scores.

### What Remains Dependent on Developer 1 (D1):
- D1's backend API endpoints (`POST /api/v1/research`, `GET /api/v1/jobs/{id}`) and Supabase persistence are not yet implemented.
- Once D1 implements `backend/app/repositories/supabase_repository.py`, D1 can serialize D3's `result.evidence_records` directly into the `field_evidence` table.
