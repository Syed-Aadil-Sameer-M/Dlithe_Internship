# Environment Setup

## 1. Purpose

This document records the development environment and setup information
collected from the project developers.

## 2. Python Environment

Python version reported by Dev1 and Dev2: 3.15.2

Backend framework and complete backend dependencies: Pending Dev1 confirmation.

## 3. Browser Automation Environment (Dev2)

- Python: 3.15.2
- Playwright: 1.65.2
- pytest: 9.2.0
- Browser: Chromium
- Chromium revision: 1255
- Chrome for Testing: 159.0.8154.6

Browser installation:

python -m playwright install chromium

Browser refresh:

python -m playwright install --force chromium

Confirmed dependencies:

- colorama==0.4.6
- greenlet==3.5.6
- iniconfig==2.3.1
- packaging==26.3
- playwright==1.65.2
- pluggy==1.7.0
- Pygments==2.21.0
- pytest==9.2.0

## 4. Scraper Detection Environment (Dev3)

- Python: 3.15.2
- pytest: 9.2.0
- BeautifulSoup4: 4.15.0

Verified local dependency snapshot:

- beautifulsoup4==4.15.0
- colorama==0.4.6
- iniconfig==2.3.1
- packaging==26.3
- pluggy==1.7.0
- Pygments==2.21.0
- pytest==9.2.0
- soupsieve==4.1.3
- typing_extensions==4.16.0

Pytest configuration:
- Configuration file: pytest.ini
- pythonpath = .
- testpaths = tests

Note: These dependency versions were verified in the D6 local virtual environment. Confirmation from Dev3 is pending.

## 5. Frontend Environment (Dev5)

- Node.js: v24.13.1
- npm: 11.8.0
- React: 19.3.1
- React DOM: 19.3.1
- Vite: 8.3.6

Frontend environment variable name:

VITE_API_BASE_URL

Frontend commands:

- npm install
- npm run dev
- npm run build
- npm run lint
- npm run preview

Dependency files:

- package.json
- package-lock.json

## 6. Backend Environment (Dev1)

Confirmed:
- Python: 3.15.2

Pending confirmation:
- Backend framework and version
- Complete backend dependency list
- Dependency management strategy
- Required environment variable names
- Backend installation and run commands
- Supabase configuration
- Health endpoint status

## 7. Database Architecture

The D6 developer plan specifies Supabase with managed PostgreSQL.

The root README currently mentions SQLite as an MVP proposal.

This architecture difference requires confirmation from Dev1 and the team before implementation.

## 8. Security Notes

- Never commit API keys, passwords, tokens or credentials.
- Store secrets in environment variables or approved CI secrets.
- Do not include real secret values in this document.
- Keep the Supabase service role key backend-only.

## 9. Status

Environment information is partially collected.

Pending items will be updated after confirmation from the respective developers.
