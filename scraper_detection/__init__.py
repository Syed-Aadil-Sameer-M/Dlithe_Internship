from scraper_detection.extraction.dom_product_extractor import (
    CrawlRecordInput,
    DOMProductExtractor,
    extract_products_dom,
    normalize_price_and_currency,
    normalize_whitespace,
)
from scraper_detection.extraction.product_extractor import (
    ExtractedProduct,
    JSONLDProductExtractor,
    SUPPORTED_PRODUCT_FIELDS,
    extract_products_json_ld,
)
from scraper_detection.schemas.evidence import (
    EvidenceMethod,
    EvidenceRecord,
    EvidenceStatus,
)

__all__ = [
    "EvidenceRecord",
    "EvidenceStatus",
    "EvidenceMethod",
    "ExtractedProduct",
    "JSONLDProductExtractor",
    "DOMProductExtractor",
    "CrawlRecordInput",
    "SUPPORTED_PRODUCT_FIELDS",
    "extract_products_json_ld",
    "extract_products_dom",
    "normalize_price_and_currency",
    "normalize_whitespace",
]
