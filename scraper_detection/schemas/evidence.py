from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class EvidenceStatus(str, Enum):
    FOUND = "Found"
    NOT_OBSERVED = "Not observed"
    UNAVAILABLE = "Unavailable"
    UNVERIFIED = "Unverified"
    BLOCKED = "Blocked"
    ERROR = "Error"

    # Deprecated alias pointing to canonical "Not observed"
    NOT_FOUND = "Not observed"


class EvidenceMethod(str, Enum):
    JSON_LD = "json_ld"
    DOM = "dom"
    REGEX = "regex"
    META = "meta"
    URL = "url"


@dataclass
class EvidenceRecord:
    field: str
    value: Any
    status: EvidenceStatus
    source_url: str
    observed_at: datetime
    method: EvidenceMethod
    confidence: float

    def __post_init__(self):
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Confidence must be between 0.0 and 1.0")


# Sample evidence records for testing the contract

sample_product_title = EvidenceRecord(
    field="product.title",
    value="Example Product",
    status=EvidenceStatus.FOUND,
    source_url="https://example.com/product/example-product",
    observed_at=datetime.now(),
    method=EvidenceMethod.JSON_LD,
    confidence=1.0,
)

sample_product_price = EvidenceRecord(
    field="product.price",
    value=999.00,
    status=EvidenceStatus.FOUND,
    source_url="https://example.com/product/example-product",
    observed_at=datetime.now(),
    method=EvidenceMethod.JSON_LD,
    confidence=1.0,
)

sample_product_currency = EvidenceRecord(
    field="product.currency",
    value="INR",
    status=EvidenceStatus.FOUND,
    source_url="https://example.com/product/example-product",
    observed_at=datetime.now(),
    method=EvidenceMethod.JSON_LD,
    confidence=1.0,
)

sample_product_missing = EvidenceRecord(
    field="product.description",
    value=None,
    status=EvidenceStatus.NOT_OBSERVED,
    source_url="https://example.com/product/example-product",
    observed_at=datetime.now(),
    method=EvidenceMethod.DOM,
    confidence=1.0,
)