# QA Matrix

## 1. Purpose

This document defines the quality assurance strategy for the E-Commerce Store Research Tool.

It identifies the major testing areas, expected results and validation status.

## 2. Testing Scope

| ID | Module | Test Area | Expected Result | Status |
|---|---|---|---|---|
| QA-01 | Backend (D1) | API health check | Health endpoint returns a successful response | Pending |
| QA-02 | Backend (D1) | URL validation | Invalid or unsafe URLs are rejected | Pending |
| QA-03 | Browser Automation (D2) | Browser launch | Chromium launches successfully | Verified |
| QA-04 | Browser Automation (D2) | Page navigation | Public pages load and return crawl information | Verified |
| QA-05 | Scraper Detection (D3) | Platform detection | Shopify, WooCommerce and Magento are identified correctly | Pending integration |
| QA-06 | Evidence & Scoring (D4) | Evidence validation | Evidence records are validated correctly | Pending integration |
| QA-07 | Evidence & Scoring (D4) | Score calculation | Scores are deterministic and within the expected range | Pending integration |
| QA-08 | Frontend (D5) | Frontend build | Production build completes successfully | Pending |
| QA-09 | Integration | Pipeline execution | Modules exchange data using agreed contracts | Pending |
| QA-10 | Deployment | Deployment smoke test | Deployed application responds successfully | Pending |

## 3. Test Categories

### Unit Testing
- Validate individual functions and modules.
- Test valid, invalid and edge-case inputs.
- Verify deterministic outputs.

### Integration Testing
- Verify communication between backend and browser automation.
- Verify CrawlBundle and EvidenceRecord contracts.
- Validate data flow between modules.

### End-to-End Testing
- Submit a store URL.
- Execute the research workflow.
- Verify the generated store profile.
- Verify frontend result display.

### Regression Testing
- Re-run existing tests after code changes.
- Ensure previously working functionality remains stable.

### Security Testing
- Validate URL safety.
- Check that secrets are not committed.
- Verify that sensitive credentials are not exposed.
- Review access controls.

## 4. Test Data

Reference platforms:
- Shopify
- WooCommerce
- Magento

Test data should use public stores and sanitized fixtures.

Each reference record should include:
- Store URL
- Platform
- Check date
- Expected fields
- Evidence source

## 5. Defect Severity

| Priority | Description |
|---|---|
| P0 | Critical failure preventing application usage |
| P1 | Major functionality failure |
| P2 | Partial functionality or incorrect results |
| P3 | Minor issue or cosmetic defect |

## 6. Test Execution Status

Testing will be updated as individual modules become available and integration progresses.

No test should be marked as passed without execution evidence.

## 7. Ownership

| Developer | Responsibility |
|---|---|
| D1 | Backend and API testing |
| D2 | Browser automation testing |
| D3 | Scraper detection testing |
| D4 | Evidence and scoring testing |
| D5 | Frontend testing |
| D6 | QA coordination, integration and release verification |

## 8. Test Harness Preparation

### 8.1 Execution Strategy
- Use pytest for Python module tests where applicable.
- Use the test commands confirmed by each module owner.
- Run integration tests after module source code is merged.
- Record test results and failures with supporting evidence.
- Do not mark tests as passed without actual execution.

### 8.2 Test Fixture Preparation
Prepare representative test data for:
- Shopify stores
- WooCommerce stores
- Magento stores

Fixtures should cover successful extraction, missing information, invalid input, and unexpected responses.

## 9. Integration Readiness Checklist

| ID | Integration Requirement | Status |
|---|---|---|
| INT-01 | D1 backend source and API contracts available | Pending |
| INT-02 | D2 CrawlBundle contract available | Pending |
| INT-03 | D3 EvidenceRecord contract available | Pending |
| INT-04 | D4 validation and scoring integration available | Pending |
| INT-05 | D5 frontend integration available | Pending |
| INT-06 | Health endpoint available | Pending |
| INT-07 | Shared test fixtures available | Pending |
| INT-08 | Integrated CI tests executable | Pending |

Update each status only after verification.

## 10. Test Evidence and Reporting

For every executed test, record:
- Test ID
- Module or component
- Execution date
- Command used
- Expected result
- Actual result
- Pass or fail status
- Related defect ID, if applicable

Test results must be supported by execution output or CI evidence.
