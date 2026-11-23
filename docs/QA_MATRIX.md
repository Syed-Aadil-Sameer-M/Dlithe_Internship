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
