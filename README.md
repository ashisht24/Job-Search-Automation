# 🤖 Job Application Automator — India

Automates job searching, cover letter generation, and applications across major Indian job portals using AI, Python  and Selenium.

The tool continuously searches for new opportunities, evaluates relevance against your CV, generates tailored cover letters using Groq AI, attempts automated applications using Selenium, and maintains a live dashboard of all job activity.

---

# Table of Contents

1. Overview
2. Features
3. Architecture
4. Supported Portals
5. Installation
6. Configuration
7. Credentials Setup
8. Usage Examples
9. Command Line Arguments
10. Continuous Monitoring Mode
11. Relevance Scoring
12. Cover Letter Generation
13. Output Files
14. Dashboard
15. Logging
16. Limitations
17. Extending the Tool
18. Security Recommendations
19. Disclaimer

---

# Overview

The application performs the following workflow:

1. Read CV PDF
2. Extract text using PDF parsers
3. Build a structured candidate profile using Groq AI
4. Search jobs across multiple portals
5. Remove duplicate jobs
6. Score relevance against your profile
7. Generate personalized cover letters
8. Attempt automated applications
9. Generate reports and dashboard
10. Repeat continuously at configurable intervals

---

# Features

## Intelligent CV Parsing

Extracts:

- Name
- Email
- Phone Number
- Skills
- Experience
- Current Role
- Education
- Professional Summary

PDF extraction pipeline:

1. pdfplumber (primary)
2. pypdf (fallback)

## Multi-Portal Job Search

Searches multiple Indian job boards simultaneously.

## AI-Based Candidate Matching

Automatically ranks jobs according to:

- Role match
- Skill match
- Resume relevance

## Automated Cover Letters

Generates custom cover letters for every relevant opportunity.

## Selenium Automation

Supports automated application workflows where possible.

## Duplicate Detection

Previously seen jobs are tracked across runs.

## Interactive Dashboard

Generates a live HTML dashboard for monitoring applications.

---

# Architecture

```text
CV PDF
   │
   ▼
CV Reader
   │
   ▼
Groq Resume Parser
   │
   ▼
Structured Candidate Profile
   │
   ▼
Portal Searchers
   │
   ▼
Job Collection
   │
   ▼
Duplicate Filtering
   │
   ▼
Relevance Scoring
   │
   ▼
Cover Letter Generation
   │
   ▼
Application Engine
   │
   ▼
Reporting + Dashboard
```

---

# Supported Portals

| Portal | Search | Auto Apply |
|----------|----------|----------|
| Naukri | ✅ | ✅ |
| LinkedIn | ✅ | ✅ Easy Apply |
| Indeed India | ✅ | ✅ Partial |
| Shine | ✅ | ✅ Partial |
| Monster India | ✅ | ⚠️ Manual |
| Instahyre | ✅ | ⚠️ Manual |

---

# Installation

## Create Virtual Environment

### Windows

```bash
python -m venv venv
venv\Scripts\activate
```

### Linux/macOS

```bash
python3 -m venv venv
source venv/bin/activate
```

## Install Dependencies

```bash
pip install selenium webdriver-manager pypdf pdfplumber groq python-dotenv requests beautifulsoup4
```

or

```bash
pip install -r requirements.txt
```

---

# Configuration

Create a `.env` file:

```env
GROQ_API_KEY=your_groq_api_key_here
```

Obtain your key from:

https://console.groq.com

Model used by the application:

```text
llama-3.3-70b-versatile
```

---

# Credentials Setup

Create:

```json
{
  "linkedin": {
    "email": "your_email@example.com",
    "password": "your_password"
  },
  "naukri": {
    "email": "your_email@example.com",
    "password": "your_password"
  },
  "indeed": {
    "email": "your_email@example.com",
    "password": "your_password"
  },
  "shine": {
    "email": "your_email@example.com",
    "password": "your_password"
  }
}
```

Save as:

```text
credentials.json
```

---

# Usage Examples

## Basic Search

```bash
python job_automator.py \
  --cv resume.pdf \
  --role "Data Scientist" \
  --location "Bangalore"
```

## Search Specific Portals

```bash
python job_automator.py \
  --cv resume.pdf \
  --role "Software Engineer" \
  --location "Mumbai" \
  --portals linkedin naukri indeed
```

## Increase Job Volume

```bash
python job_automator.py \
  --cv resume.pdf \
  --role "ML Engineer" \
  --max-jobs 25
```

## Adjust Relevance Threshold

```bash
python job_automator.py \
  --cv resume.pdf \
  --role "Backend Engineer" \
  --min-score 0.6
```

## Cover Letters Only

```bash
python job_automator.py \
  --cv resume.pdf \
  --role "Data Analyst" \
  --skip-apply
```

## Actual Application Mode

```bash
python job_automator.py \
  --cv resume.pdf \
  --role "Product Manager" \
  --apply
```

## Headless Mode

```bash
python job_automator.py \
  --cv resume.pdf \
  --role "DevOps Engineer" \
  --apply \
  --headless
```

## Run Every 10 Minutes

```bash
python job_automator.py \
  --cv resume.pdf \
  --role "AI Engineer" \
  --interval 10
```

---

# Command Line Arguments

| Argument | Required | Default | Description |
|----------|----------|----------|----------|
| --cv | Yes | - | CV PDF |
| --role | Yes | - | Target role |
| --location | No | Bangalore | Preferred location |
| --portals | No | All | Portals to search |
| --max-jobs | No | 10 | Jobs per portal |
| --min-score | No | 0.4 | Relevance threshold |
| --apply | No | False | Enable application mode |
| --headless | No | False | Run browser headless |
| --skip-apply | No | False | Skip application phase |
| --creds | No | credentials.json | Credentials file |
| --interval | No | 30 | Minutes between scans |

---

# Continuous Monitoring Mode

The application runs forever until stopped.

Per cycle:

1. Search jobs
2. Remove duplicates
3. Score jobs
4. Generate cover letters
5. Apply if enabled
6. Update dashboard
7. Sleep
8. Repeat

Stop using:

```text
Ctrl + C
```

---

# Relevance Scoring

Current scoring includes:

### Title Match

Strong weighting when target role appears in job title.

### Skill Match

Matches CV skills against available job content.

### Combined Score

Final score range:

```text
0.0 - 1.0
```

Default threshold:

```text
0.4
```

---

# Cover Letter Generation

Groq AI receives:

- Candidate information
- Experience
- Education
- Skills
- Job title
- Company
- Description

Generated cover letters:

- Professional
- Concise
- Personalized
- Under 300 words

---

# Output Files

Project structure:

```text
job_apply/
├── job_automator.py
├── credentials.json
├── .env
├── requirements.txt
├── job_automator.log
└── output/
```

## Timestamped Job Archives

```text
output/jobs_YYYYMMDD_HHMMSS.json
```

Contains:

- Job details
- Relevance score
- Cover letter
- Application status

## Rolling Job Database

```text
output/all_jobs.json
```

Maintains every discovered job across all cycles.

## Seen Job Registry

```text
output/seen_jobs.json
```

Prevents duplicate processing.

## Cover Letter Repository

```text
output/cover_letters_YYYYMMDD_HHMMSS/
```

Contains one text file per generated cover letter.

---

# Dashboard

Generated automatically:

```text
output/dashboard.html
```

Features:

- Total jobs
- Applied jobs
- Pending jobs
- Portal statistics
- Application status
- Cover letter viewer
- Job links
- Notes and errors

Open directly in your browser.

---

# Logging

Logs are written to:

```text
job_automator.log
```

Tracks:

- CV parsing
- Searches
- Relevance scoring
- Cover letter generation
- Applications
- Dashboard updates
- Errors

---

# Limitations

- Job portals may change HTML structures.
- CAPTCHA challenges may require manual intervention.
- Some portals actively block automation.
- Scanned PDFs without OCR are not supported.
- Auto-apply success depends on portal-specific workflows.

---

# Extending the Tool

Create a scraper:

```python
class NewPortalScraper:
    def search(self, role, location, max_jobs=10):
        pass
```

Register:

```python
PORTALS = {
    "newportal": NewPortalScraper
}
```

Then use:

```bash
python job_automator.py --portals newportal
```

---

# Security Recommendations

- Never commit credentials.json
- Add credentials.json to .gitignore
- Protect your .env file
- Use dedicated portal accounts where possible
- Review generated applications before submission

---

# Disclaimer

This project is intended for educational and personal productivity purposes.

Users are responsible for complying with:

- Job portal Terms of Service
- Local laws
- Employer application policies

Use responsibly and verify all generated applications before submission.
