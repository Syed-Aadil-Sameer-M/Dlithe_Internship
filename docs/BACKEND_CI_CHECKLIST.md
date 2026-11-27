# Backend CI Integration Checklist

## 1. Purpose

This document defines the steps for integrating D1 backend checks into the existing GitHub Actions CI workflow.

## 2. Backend Requirements

| Requirement | Expected Configuration |
|---|---|
| Python | 3.15 |
| Framework | FastAPI |
| ASGI Server | Uvicorn |
| Entry Point | app.main:app |
| Port | 8000 |
| Health Endpoint | GET /health |
| Testing Framework | pytest |
| Dependency File | requirements.txt |

Note: These requirements are based on D1's Backend Handoff Report and must be verified against the actual implementation.

## 3. Backend Source Verification

Before configuring backend CI, verify:

- [ ] Backend source code is available.
- [ ] requirements.txt exists.
- [ ] app/main.py exists.
- [ ] API routes are implemented.
- [ ] Database configuration is available.
- [ ] Backend test files are available.
- [ ] Health endpoint is implemented.

## 4. CI Execution Steps

The backend CI job should perform the following checks:

| Step | Action | Expected Result |
|---|---|---|
| 1 | Checkout repository | Source code available |
| 2 | Verify backend files | Required files found |
| 3 | Set up Python | Python environment ready |
| 4 | Install dependencies | Installation successful |
| 5 | Run pytest | Backend tests pass |
| 6 | Start FastAPI | Server starts successfully |
| 7 | Test /health | HTTP 200 response |
| 8 | Validate response | Expected JSON received |

## 5. Health Check Validation

Endpoint: GET /health

Expected HTTP status: 200

Expected response:

{"status": "OK"}

The health check must only be marked passed after actual execution.

## 6. Docker Validation

Once backend source code is available:

- [ ] Verify Dockerfile.
- [ ] Build backend Docker image.
- [ ] Confirm image builds successfully.
- [ ] Start backend container.
- [ ] Verify container startup.
- [ ] Test the health endpoint inside the running container.
- [ ] Record build and runtime failures.

## 7. CI Workflow Integration

The existing workflow is:

.github/workflows/ci.yml

A backend-tests job will be added to the existing workflow when the backend implementation is available.

Existing jobs:
- D3 Python Tests
- Frontend Lint and Build

New planned job:
- Backend Tests

The backend job must report missing source files clearly rather than incorrectly reporting successful tests.

## 8. Failure Handling

| Failure | D6 Action |
|---|---|
| Missing backend files | Report to D1 |
| Dependency installation failure | Record error and notify D1 |
| Backend test failure | Record test evidence and notify owner |
| Server startup failure | Report startup error |
| Health check failure | Record HTTP response and notify D1 |
| Docker build failure | Record build logs |
| Container failure | Investigate logs and report findings |

D6 coordinates testing and integration. Backend implementation fixes remain the responsibility of D1.

## 9. Deployment Readiness

Before Render feasibility testing:

- [ ] Backend Docker image builds successfully.
- [ ] Container starts successfully.
- [ ] Application listens on the required interface and port.
- [ ] Health endpoint responds successfully.
- [ ] Required environment variables are configured securely.
- [ ] Browser execution requirements are validated.
- [ ] Hosting feasibility results are documented.

## 10. Current Execution Status

| Activity | Status |
|---|---|
| Existing CI workflow reviewed | Completed |
| Existing D3 tests verified green | Completed |
| Existing frontend build verified green | Completed |
| Backend CI plan prepared | Completed |
| Backend source verification | Pending D1 |
| Backend dependency verification | Pending D1 |
| Backend pytest execution | Pending D1 |
| Backend health check | Pending D1 |
| Backend Docker build | Pending D1 |
| Render feasibility test | Pending |

## 11. Ownership

D1:
- Backend implementation
- Dependencies
- API routes
- Backend unit tests
- Health endpoint

D6:
- CI workflow integration
- Docker validation
- Integration testing
- QA evidence
- Deployment feasibility coordination
- Release verification

## 12. Test Evidence

For every executed check, record:

- Test name
- Execution date
- Command used
- Expected result
- Actual result
- Pass/fail status
- Supporting logs
- Related issue, if any

No test should be marked passed without execution evidence.
