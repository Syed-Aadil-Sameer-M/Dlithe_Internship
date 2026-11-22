from scraper_detection.detection.platform_detector import (
    FingerprintIndicator,
    PLATFORM_MAGENTO,
    PLATFORM_RULES,
    PLATFORM_SHOPIFY,
    PLATFORM_WOOCOMMERCE,
    PlatformDetectionResult,
    PlatformDetector,
    PlatformFingerprintRule,
    detect_ecommerce_platform,
)
from scraper_detection.extraction.contact_social_extractor import (
    SUPPORTED_CONTACT_FIELDS,
    ContactSocialExtractor,
    ExtractedContactSocial,
    extract_contact_and_social,
)
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
from scraper_detection.extraction.store_extractor import (
    SUPPORTED_STORE_FIELDS,
    ExtractedStoreDetails,
    StoreExtractor,
    extract_store_details,
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
    "SUPPORTED_STORE_FIELDS",
    "ExtractedStoreDetails",
    "StoreExtractor",
    "extract_store_details",
    "SUPPORTED_CONTACT_FIELDS",
    "ExtractedContactSocial",
    "ContactSocialExtractor",
    "extract_contact_and_social",
    "PlatformDetector",
    "detect_ecommerce_platform",
    "PlatformDetectionResult",
    "FingerprintIndicator",
    "PlatformFingerprintRule",
    "PLATFORM_RULES",
    "PLATFORM_SHOPIFY",
    "PLATFORM_WOOCOMMERCE",
    "PLATFORM_MAGENTO",
]
