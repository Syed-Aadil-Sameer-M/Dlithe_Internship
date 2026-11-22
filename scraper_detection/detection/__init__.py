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

__all__ = [
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
