# E-Commerce Store Research Tool

An automated research platform that analyses online stores, collects publicly available information, detects e-commerce and marketing technologies, and generates structured research reports.

> **Project status:** Under Development  
> **Target:** 3-Week MVP  
> **Documentation:** Version 1.0

---

## 1. Project Overview

The E-Commerce Store Research Tool aims to automate the process of researching online stores for sales and marketing outreach.

The application accepts an online store name or URL, verifies the website, crawls selected public pages, extracts relevant information, identifies e-commerce and marketing technologies, and generates an evidence-based store profile.

The primary objective is to reduce manual research time, improve data consistency, and provide useful insights for business development.

### Project Objectives

- Automate online store research.
- Identify e-commerce platforms and marketing technologies.
- Extract product details, prices, social links and contact information.
- Detect email/SMS signup forms and promotional offers.
- Generate AI-assisted marketing insights using validated evidence.
- Calculate an explainable store fit score.
- Export research results in JSON, Excel and PDF formats.

## 2. Key Features

| Feature | Description |
|---|---|
| Store Identification | Accepts store names or URLs and verifies websites |
| Website Crawling | Crawls selected public pages |
| Product Extraction | Collects product names, prices and URLs |
| Technology Detection | Identifies e-commerce platforms |
| Marketing Detection | Detects email, SMS and review applications |
| Popup Detection | Checks for signup forms and discount offers |
| Social Research | Extracts publicly available social media links |
| Contact Extraction | Identifies publicly displayed contact information |
| AI Analysis | Generates evidence-based marketing summaries |
| Fit Scoring | Calculates an explainable store suitability score |
| Report Generation | Exports JSON, Excel and PDF reports |

## 3. Application Workflow

1. User enters an online store name or URL.
2. Backend validates the input and checks website accessibility.
3. Browser automation visits selected public pages.
4. HTML parsing extracts relevant store information.
5. Technology detection identifies platforms and marketing tools.
6. Dynamic checks identify observable popups and signup forms.
7. Validation and normalisation organise collected information.
8. AI optionally generates a marketing-gap summary.
9. Scoring logic calculates the store fit score.
10. Report generation produces JSON, Excel and PDF reports.

## 4. Proposed Technology Stack

The following technologies are planned for the MVP. Specific versions, dependencies and deployment choices may change during development.

| Layer | Technology | Purpose |
|---|---|---|
| Frontend | React | User interface and dashboard |
| Backend | Python + FastAPI | REST API and application logic |
| Browser Automation | Playwright | JavaScript-rendered website crawling |
| HTML Parsing | BeautifulSoup4 | Extracting website information |
| Pattern Extraction | Python Regex | Email, phone and text extraction |
| Store Lookup | DuckDuckGo Search + RapidFuzz | Store discovery and matching |
| Technology Detection | Python-based rules | E-commerce and marketing technology detection |
| AI Integration | Groq API (optional) | Marketing summaries and interpretation |
| Data Processing | Pandas | Data processing |
| Excel Export | OpenPyXL | Spreadsheet generation |
| PDF Export | ReportLab | PDF report generation |
| Database | SQLite (MVP proposal) | Storing profiles and crawl history |
| Version Control | Git + GitHub | Team collaboration |
| CI/CD | GitHub Actions | Automated testing and integration |
| Deployment | Render / Netlify or approved alternatives | Hosting |

## 5. Planned Application Architecture

The application follows a modular architecture. Each module has a specific responsibility to support independent development, testing and integration.

| Module | Responsibility |
|---|---|
| Frontend (React) | User input, progress display, results and report downloads |
| `app.py` | FastAPI application entry point |
| `store_lookup.py` | Store URL validation and lookup |
| `browser.py` | Playwright browser automation |
| `scraper.py` | Product, social and contact extraction |
| `technology_detector.py` | E-commerce and marketing technology detection |
| `popup_detector.py` | Popup and signup form detection |
| `ai_analyzer.py` | Optional Groq AI integration |
| `validation.py` | Data validation and normalisation |
| `scoring.py` | Explainable store fit scoring |
| `storage.py` | Data persistence and crawl history |
| `report_generator.py` | JSON, Excel and PDF report generation |

## 6. Planned Folder Structure

```text
ecommerce-research-tool/
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── services/
│   │   ├── App.jsx
│   │   └── main.jsx
│   ├── public/
│   └── package.json
│
├── backend/
│   ├── app.py
│   ├── store_lookup.py
│   ├── browser.py
│   ├── scraper.py
│   ├── technology_detector.py
│   ├── popup_detector.py
│   ├── ai_analyzer.py
│   ├── validation.py
│   ├── scoring.py
│   ├── storage.py
│   └── report_generator.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── e2e/
│   └── fixtures/
│
├── output/
├── docs/
├── .github/
│   └── workflows/
│       └── ci.yml
│
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

*This is a proposed structure. Actual folders and files will be updated as implementation progresses.*

## 7. Development Roadmap

### Week 1 – Foundation and Scraping

- Establish project structure and development environment.
- Implement FastAPI backend.
- Validate store URLs and website accessibility.
- Build Playwright crawler.
- Extract basic product information and social links.
- Generate the first validated JSON record.

### Week 2 – Detection, Analysis and Reports

- Implement e-commerce and marketing technology detection.
- Add popup and signup form detection.
- Implement validation and normalisation.
- Develop the store fit scoring system.
- Integrate optional Groq AI analysis.
- Generate JSON, Excel and PDF reports.
- Develop the React frontend.

### Week 3 – Testing, Deployment and Handoff

- Perform unit, integration and end-to-end testing.
- Validate results against manually researched stores.
- Fix high-priority issues.
- Measure performance and reliability.
- Deploy the application.
- Prepare documentation and final handoff.

## 8. Quality Assurance

Testing will cover:

- Valid and invalid store URLs.
- Website redirects and unreachable domains.
- Slow and JavaScript-heavy websites.
- Missing product and contact information.
- Duplicate product records.
- Blocked websites and partial crawl failures.
- AI API failures and quota limits.
- JSON, Excel and PDF export accuracy.

### Data Status Values

Every collected field should use an appropriate status:

- `Found`
- `Not found`
- `Unavailable`
- `Unverified`
- `Blocked`

Missing information must never be invented or treated as confirmed negative evidence.

## 9. Security and Responsible Usage

- Collect only publicly accessible information.
- Store API keys and sensitive configuration in environment variables.
- Never commit `.env` files or API credentials.
- Use `.env.example` for documenting configuration.
- Validate URLs and prevent access to private or local network addresses.
- Respect website access restrictions, applicable laws and approved crawl policies.
- Do not bypass CAPTCHAs, logins, paywalls or anti-bot protections.
- Minimise personal data collection.

## 10. Getting Started

### Prerequisites

- Python (team-approved version)
- Node.js and npm
- Git
- Visual Studio Code or another suitable IDE
- Required project dependencies

### Clone the Repository

```bash
git clone <repository-url>
```

### Navigate to the Project

```bash
cd ecommerce-research-tool
```

### Backend Setup

Create a virtual environment:

```bash
python -m venv venv
```

Activate it on Windows:

```bash
venv\Scripts\activate
```

Install dependencies after the team finalises `requirements.txt`:

```bash
pip install -r requirements.txt
```

### Frontend Setup

After the React project and its `package.json` are available:

```bash
cd frontend
npm install
```

Start the React development server using the script configured in `package.json`:

```bash
npm run dev
```

### Environment Configuration

Create a local `.env` file using `.env.example` as a reference.

Add required configuration values. Never push API keys or secrets to GitHub.

*Exact setup commands and dependency versions will be updated when the development environment is finalised.*

## 11. Deployment

Planned deployment options:

- **Frontend:** Netlify or company-approved hosting.
- **Backend:** Render or company-approved hosting.
- **AI:** Groq API (optional).
- **CI/CD:** GitHub Actions.

Final deployment choices will depend on browser dependencies, hosting limits, memory usage, performance and company requirements.

## 12. Team Collaboration

The project uses Git and GitHub for collaborative development.

Development guidelines:

1. Work on individual feature branches.
2. Use meaningful commit messages.
3. Create Pull Requests for code changes.
4. Follow the shared Pull Request template.
5. Run relevant tests before submitting changes.
6. Review integration impacts before merging.
7. Follow repository branch protection rules.

## 13. Future Enhancements

- Bulk store research.
- Advanced research dashboard.
- Historical store analysis.
- Expanded technology fingerprint database.
- Enhanced reporting and analytics.
- Scalable database and multi-user support.

## 14. Project Status

| Item | Status |
|---|---|
| Project planning | Completed |
| Repository setup | In progress |
| Development environment | In progress |
| Backend implementation | Planned |
| React frontend implementation | Planned |
| Automated testing | Planned |
| Deployment | Planned |

---

## Important Documentation Note

This README represents the current project plan, not a guarantee that every proposed technology or feature has been implemented.

Technology choices, dependencies, architecture, folder structure and deployment configurations may evolve during development. This document will be updated to reflect the actual implementation and team-approved decisions.

---

**E-Commerce Store Research Tool**

*Automating e-commerce research through evidence-based data collection, technology detection and intelligent analysis.*