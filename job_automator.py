"""
Job Application Automator
=========================
1. Reads your CV (PDF)
2. Searches for relevant jobs on Naukri, LinkedIn, Indeed, Shine, Monster India, Instahyre
3. Drafts tailored cover letters using Groq AI
4. Attempts automated application via Selenium

Usage:
    python job_automator.py --cv path/to/cv.pdf --role "Data Scientist" --location "Bangalore"

Requirements:
    pip install selenium webdriver-manager pypdf pdfplumber groq python-dotenv requests beautifulsoup4
"""

import os
import re
import time
import json
import random
import logging
import argparse
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional

import requests
import pdfplumber
from pypdf import PdfReader
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from groq import Groq

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, WebDriverException
)
from webdriver_manager.chrome import ChromeDriverManager

# ─────────────────────────────────────────────
# Configuration & Logging
# ─────────────────────────────────────────────
load_dotenv()

# Fix Windows console Unicode issue (cp1252 can't handle emojis)
import sys
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(stream=sys.stdout),
        logging.FileHandler("job_automator.log", encoding="utf-8")
    ]
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# Data Models
# ─────────────────────────────────────────────
@dataclass
class JobListing:
    title: str
    company: str
    location: str
    portal: str
    url: str
    description: str = ""
    salary: str = ""
    experience: str = ""
    relevance_score: float = 0.0
    cover_letter: str = ""
    applied: bool = False
    applied_at: str = ""
    notes: str = ""


@dataclass
class CVProfile:
    raw_text: str = ""
    name: str = ""
    email: str = ""
    phone: str = ""
    skills: list = field(default_factory=list)
    experience_years: str = ""
    current_role: str = ""
    education: str = ""
    summary: str = ""


# ─────────────────────────────────────────────
# Step 1: CV Reader
# ─────────────────────────────────────────────
class CVReader:
    def read(self, pdf_path: str) -> CVProfile:
        log.info(f"📄 Reading CV: {pdf_path}")
        text = self._extract_text(pdf_path)
        if not text.strip():
            raise ValueError("Could not extract text from CV. Ensure it's not a scanned image PDF.")
        profile = self._parse_with_groq(text)
        profile.raw_text = text
        log.info(f"✅ CV parsed — Name: {profile.name}, Skills: {len(profile.skills)} found")
        return profile

    def _extract_text(self, pdf_path: str) -> str:
        # Try pdfplumber first (better for complex layouts)
        try:
            with pdfplumber.open(pdf_path) as pdf:
                pages = [p.extract_text() or "" for p in pdf.pages]
                text = "\n".join(pages)
                if len(text.strip()) > 100:
                    return text
        except Exception:
            pass
        # Fallback to pypdf
        reader = PdfReader(pdf_path)
        return "\n".join(p.extract_text() or "" for p in reader.pages)

    def _parse_with_groq(self, text: str) -> CVProfile:
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        if not api_key or api_key == "your_groq_api_key_here":
            raise ValueError(
                "\n\nGROQ_API_KEY is missing or not set!\n"
                "  1. Open the .env file in the job_apply folder\n"
                "  2. Replace your_groq_api_key_here with your real key\n"
                "  3. Get a free key at: https://console.groq.com\n"
            )
        client = Groq(api_key=api_key)
        prompt = f"""Extract structured information from this CV/resume text.
Return ONLY valid JSON with these exact keys:
{{
  "name": "full name",
  "email": "email address",
  "phone": "phone number",
  "skills": ["skill1", "skill2", ...],
  "experience_years": "e.g. 5 years",
  "current_role": "most recent job title",
  "education": "highest qualification",
  "summary": "2-3 sentence professional summary"
}}

CV TEXT:
{text[:6000]}
"""
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000
        )
        raw = response.choices[0].message.content.strip()
        # Strip markdown fences if present
        raw = re.sub(r"^```json\s*|\s*```$", "", raw, flags=re.MULTILINE).strip()
        data = json.loads(raw)
        return CVProfile(
            name=data.get("name", ""),
            email=data.get("email", ""),
            phone=data.get("phone", ""),
            skills=data.get("skills", []),
            experience_years=data.get("experience_years", ""),
            current_role=data.get("current_role", ""),
            education=data.get("education", ""),
            summary=data.get("summary", "")
        )


# ─────────────────────────────────────────────
# Step 2: Job Searchers (per portal)
# ─────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


class NaukriScraper:
    BASE = "https://www.naukri.com"

    def search(self, role: str, location: str, max_jobs: int = 10) -> list[JobListing]:
        log.info(f"🔍 Naukri: searching '{role}' in '{location}'")
        jobs = []
        try:
            role_slug = role.replace(" ", "-").lower()
            loc_slug = location.replace(" ", "-").lower()
            url = f"{self.BASE}/{role_slug}-jobs-in-{loc_slug}"
            resp = requests.get(url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select("article.jobTuple, div.job-post, div[class*='jobTuple']")[:max_jobs]
            for card in cards:
                try:
                    title_el = card.select_one("a.title, a[class*='title']")
                    company_el = card.select_one("a.subTitle, a[class*='company']")
                    loc_el = card.select_one("li[class*='location'], span[class*='location']")
                    exp_el = card.select_one("li[class*='experience'], span[class*='experience']")
                    sal_el = card.select_one("li[class*='salary'], span[class*='salary']")
                    if not title_el:
                        continue
                    jobs.append(JobListing(
                        title=title_el.get_text(strip=True),
                        company=company_el.get_text(strip=True) if company_el else "N/A",
                        location=loc_el.get_text(strip=True) if loc_el else location,
                        portal="Naukri",
                        url=title_el.get("href", url),
                        experience=exp_el.get_text(strip=True) if exp_el else "",
                        salary=sal_el.get_text(strip=True) if sal_el else ""
                    ))
                except Exception:
                    continue
        except Exception as e:
            log.warning(f"Naukri scrape failed: {e}")
        # Fallback: direct search URL as single entry if scraping fails
        if not jobs:
            jobs.append(JobListing(
                title=f"{role} (Search Results)",
                company="Multiple",
                location=location,
                portal="Naukri",
                url=f"https://www.naukri.com/{role.replace(' ', '-').lower()}-jobs-in-{location.replace(' ', '-').lower()}"
            ))
        log.info(f"  → {len(jobs)} jobs from Naukri")
        return jobs


class IndeedScraper:
    BASE = "https://in.indeed.com"

    def search(self, role: str, location: str, max_jobs: int = 10) -> list[JobListing]:
        log.info(f"🔍 Indeed India: searching '{role}' in '{location}'")
        jobs = []
        try:
            params = {"q": role, "l": location, "fromage": "7"}
            resp = requests.get(f"{self.BASE}/jobs", params=params, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select("div.job_seen_beacon, div[class*='jobCard']")[:max_jobs]
            for card in cards:
                try:
                    title_el = card.select_one("h2.jobTitle a, a[class*='jcs-JobTitle']")
                    company_el = card.select_one("span[class*='companyName'], div[class*='company']")
                    loc_el = card.select_one("div[class*='companyLocation'], span[class*='location']")
                    sal_el = card.select_one("div[class*='salary'], span[class*='salary']")
                    if not title_el:
                        continue
                    href = title_el.get("href", "")
                    full_url = f"{self.BASE}{href}" if href.startswith("/") else href
                    jobs.append(JobListing(
                        title=title_el.get_text(strip=True),
                        company=company_el.get_text(strip=True) if company_el else "N/A",
                        location=loc_el.get_text(strip=True) if loc_el else location,
                        portal="Indeed",
                        url=full_url,
                        salary=sal_el.get_text(strip=True) if sal_el else ""
                    ))
                except Exception:
                    continue
        except Exception as e:
            log.warning(f"Indeed scrape failed: {e}")
        if not jobs:
            jobs.append(JobListing(
                title=f"{role} (Search Results)",
                company="Multiple",
                location=location,
                portal="Indeed",
                url=f"https://in.indeed.com/jobs?q={role.replace(' ', '+')}&l={location}"
            ))
        log.info(f"  → {len(jobs)} jobs from Indeed")
        return jobs


class LinkedInScraper:
    BASE = "https://www.linkedin.com"

    def search(self, role: str, location: str, max_jobs: int = 10) -> list[JobListing]:
        log.info(f"🔍 LinkedIn: searching '{role}' in '{location}'")
        jobs = []
        try:
            params = {
                "keywords": role, "location": location,
                "f_TPR": "r604800", "position": 1, "pageNum": 0
            }
            resp = requests.get(
                f"{self.BASE}/jobs/search/", params=params,
                headers=HEADERS, timeout=15
            )
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select("div.base-card, li.jobs-search-results__list-item")[:max_jobs]
            for card in cards:
                try:
                    title_el = card.select_one("h3.base-search-card__title, a.job-card-list__title")
                    company_el = card.select_one("h4.base-search-card__subtitle, a.job-card-container__company-name")
                    loc_el = card.select_one("span.job-search-card__location, li.job-card-container__metadata-item")
                    link_el = card.select_one("a.base-card__full-link, a[class*='job-card']")
                    if not title_el:
                        continue
                    jobs.append(JobListing(
                        title=title_el.get_text(strip=True),
                        company=company_el.get_text(strip=True) if company_el else "N/A",
                        location=loc_el.get_text(strip=True) if loc_el else location,
                        portal="LinkedIn",
                        url=link_el.get("href", "") if link_el else ""
                    ))
                except Exception:
                    continue
        except Exception as e:
            log.warning(f"LinkedIn scrape failed: {e}")
        if not jobs:
            jobs.append(JobListing(
                title=f"{role} (Search Results)",
                company="Multiple",
                location=location,
                portal="LinkedIn",
                url=f"https://www.linkedin.com/jobs/search/?keywords={role.replace(' ', '%20')}&location={location}"
            ))
        log.info(f"  → {len(jobs)} jobs from LinkedIn")
        return jobs


class ShineScraper:
    def search(self, role: str, location: str, max_jobs: int = 10) -> list[JobListing]:
        log.info(f"🔍 Shine.com: searching '{role}' in '{location}'")
        jobs = []
        try:
            params = {"q": role, "loc": location}
            resp = requests.get("https://www.shine.com/job-search/jobs", params=params, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select("div.jobCard, article[class*='job']")[:max_jobs]
            for card in cards:
                try:
                    title_el = card.select_one("h2 a, h3 a, a[class*='title']")
                    company_el = card.select_one("span[class*='company'], div[class*='company']")
                    loc_el = card.select_one("span[class*='location'], li[class*='location']")
                    if not title_el:
                        continue
                    href = title_el.get("href", "")
                    jobs.append(JobListing(
                        title=title_el.get_text(strip=True),
                        company=company_el.get_text(strip=True) if company_el else "N/A",
                        location=loc_el.get_text(strip=True) if loc_el else location,
                        portal="Shine",
                        url=f"https://www.shine.com{href}" if href.startswith("/") else href
                    ))
                except Exception:
                    continue
        except Exception as e:
            log.warning(f"Shine scrape failed: {e}")
        if not jobs:
            jobs.append(JobListing(
                title=f"{role} (Search Results)",
                company="Multiple",
                location=location,
                portal="Shine",
                url=f"https://www.shine.com/job-search/jobs?q={role.replace(' ', '+')}&loc={location}"
            ))
        log.info(f"  → {len(jobs)} jobs from Shine")
        return jobs


class MonsterScraper:
    def search(self, role: str, location: str, max_jobs: int = 10) -> list[JobListing]:
        log.info(f"🔍 Monster India: searching '{role}' in '{location}'")
        jobs = []
        try:
            params = {"q": role, "where": location}
            resp = requests.get("https://www.monsterindia.com/srp/results", params=params, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select("div.card-body, div[class*='jobCard']")[:max_jobs]
            for card in cards:
                try:
                    title_el = card.select_one("h3 a, a[class*='title']")
                    company_el = card.select_one("span[class*='company']")
                    loc_el = card.select_one("span[class*='location']")
                    if not title_el:
                        continue
                    href = title_el.get("href", "")
                    jobs.append(JobListing(
                        title=title_el.get_text(strip=True),
                        company=company_el.get_text(strip=True) if company_el else "N/A",
                        location=loc_el.get_text(strip=True) if loc_el else location,
                        portal="Monster India",
                        url=f"https://www.monsterindia.com{href}" if href.startswith("/") else href
                    ))
                except Exception:
                    continue
        except Exception as e:
            log.warning(f"Monster India scrape failed: {e}")
        if not jobs:
            jobs.append(JobListing(
                title=f"{role} (Search Results)",
                company="Multiple",
                location=location,
                portal="Monster India",
                url=f"https://www.monsterindia.com/srp/results?q={role.replace(' ', '+')}&where={location}"
            ))
        log.info(f"  → {len(jobs)} jobs from Monster India")
        return jobs


class InstahyreScraper:
    def search(self, role: str, location: str, max_jobs: int = 10) -> list[JobListing]:
        log.info(f"🔍 Instahyre: searching '{role}' in '{location}'")
        # Instahyre uses JS rendering; return search URL as a listing
        jobs = [JobListing(
            title=f"{role} (Search Results)",
            company="Multiple",
            location=location,
            portal="Instahyre",
            url=f"https://www.instahyre.com/candidate/jobs/?title={role.replace(' ', '+')}&location={location}"
        )]
        log.info(f"  → 1 job portal entry from Instahyre")
        return jobs


# ─────────────────────────────────────────────
# Step 3: Relevance Filter + Cover Letter
# ─────────────────────────────────────────────
class JobMatcher:
    def __init__(self):
        api_key = os.getenv("GROQ_API_KEY")
        self.client = Groq(api_key=api_key)

    def score_and_filter(
        self, jobs: list[JobListing], profile: CVProfile,
        target_role: str, min_score: float = 0.5
    ) -> list[JobListing]:
        log.info(f"🎯 Scoring {len(jobs)} jobs for relevance...")
        scored = []
        for job in jobs:
            score = self._score_job(job, profile, target_role)
            job.relevance_score = score
            if score >= min_score:
                scored.append(job)
        scored.sort(key=lambda j: j.relevance_score, reverse=True)
        log.info(f"  → {len(scored)} jobs passed relevance filter (min score: {min_score})")
        return scored

    def _score_job(self, job: JobListing, profile: CVProfile, target_role: str) -> float:
        title_lower = job.title.lower()
        role_lower = target_role.lower()
        skills_lower = [s.lower() for s in profile.skills]
        desc_lower = (job.description + " " + job.title).lower()

        score = 0.0
        # Title match
        if role_lower in title_lower or any(w in title_lower for w in role_lower.split()):
            score += 0.5
        # Skills match
        matched_skills = sum(1 for s in skills_lower if s in desc_lower)
        if profile.skills:
            score += 0.5 * min(matched_skills / max(len(profile.skills), 1), 1.0)
        return round(min(score, 1.0), 2)

    def draft_cover_letter(self, job: JobListing, profile: CVProfile) -> str:
        log.info(f"  ✍️  Drafting cover letter for: {job.title} at {job.company}")
        prompt = f"""Write a professional, concise cover letter for this job application.

CANDIDATE PROFILE:
- Name: {profile.name}
- Current Role: {profile.current_role}
- Experience: {profile.experience_years}
- Skills: {', '.join(profile.skills[:15])}
- Education: {profile.education}
- Summary: {profile.summary}

JOB DETAILS:
- Title: {job.title}
- Company: {job.company}
- Location: {job.location}
- Portal: {job.portal}
- Description: {job.description[:500] if job.description else 'Not available'}

Write a 3-paragraph cover letter (opening, body with specific skills match, closing with CTA).
Keep it under 300 words. Do not use placeholders like [Your Name] — use actual details provided.
"""
        response = self.client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600
        )
        return response.choices[0].message.content.strip()


# ─────────────────────────────────────────────
# Step 4: Selenium Applicator
# ─────────────────────────────────────────────
class SeleniumApplicator:
    def __init__(self, headless: bool = False):
        self.headless = headless
        self.driver = None

    def _init_driver(self):
        opts = Options()
        if self.headless:
            opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--window-size=1280,900")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=opts)
        self.driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        log.info("🌐 Browser launched")

    def _wait(self, by, selector, timeout=10):
        return WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located((by, selector))
        )

    def _slow_type(self, el, text: str):
        for ch in text:
            el.send_keys(ch)
            time.sleep(random.uniform(0.03, 0.08))

    def apply_all(
        self, jobs: list[JobListing], profile: CVProfile,
        cv_path: str, credentials: dict, dry_run: bool = False
    ) -> list[JobListing]:
        if not jobs:
            return jobs
        self._init_driver()
        try:
            for job in jobs:
                if job.applied:
                    continue
                log.info(f"\n🚀 Applying: {job.title} @ {job.company} [{job.portal}]")
                try:
                    if dry_run:
                        log.info("  [DRY RUN] Opening job page in browser...")
                        self.driver.get(job.url)
                        time.sleep(2)
                        job.notes = "Dry run — page opened"
                    else:
                        success = self._dispatch_apply(job, profile, cv_path, credentials)
                        if success:
                            job.applied = True
                            job.applied_at = datetime.now().isoformat()
                            log.info(f"  ✅ Applied successfully")
                        else:
                            job.notes = "Apply step incomplete — manual action needed"
                            log.warning(f"  ⚠️  Could not fully automate — manual steps required")
                except Exception as e:
                    job.notes = f"Error: {e}"
                    log.error(f"  ❌ Error applying: {e}")
                time.sleep(random.uniform(3, 6))
        finally:
            if self.driver:
                self.driver.quit()
        return jobs

    def _dispatch_apply(
        self, job: JobListing, profile: CVProfile,
        cv_path: str, credentials: dict
    ) -> bool:
        portal = job.portal.lower()
        if "naukri" in portal:
            return self._apply_naukri(job, profile, cv_path, credentials.get("naukri", {}))
        elif "indeed" in portal:
            return self._apply_indeed(job, profile, credentials.get("indeed", {}))
        elif "linkedin" in portal:
            return self._apply_linkedin(job, profile, credentials.get("linkedin", {}))
        elif "shine" in portal:
            return self._apply_shine(job, profile, credentials.get("shine", {}))
        else:
            # Generic: open page for manual apply
            self.driver.get(job.url)
            time.sleep(3)
            job.notes = "Page opened — apply manually"
            return False

    # ── Naukri ──────────────────────────────────────────────────────────────
    def _apply_naukri(self, job: JobListing, profile: CVProfile, cv_path: str, creds: dict) -> bool:
        try:
            self.driver.get("https://www.naukri.com/nlogin/login")
            time.sleep(2)
            email_el = self._wait(By.ID, "usernameField")
            self._slow_type(email_el, creds.get("email", profile.email))
            pwd_el = self.driver.find_element(By.ID, "passwordField")
            self._slow_type(pwd_el, creds.get("password", ""))
            pwd_el.submit()
            time.sleep(3)
            self.driver.get(job.url)
            time.sleep(3)
            apply_btn = WebDriverWait(self.driver, 8).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(),'Apply')]"))
            )
            apply_btn.click()
            time.sleep(3)
            return True
        except Exception as e:
            log.debug(f"Naukri apply error: {e}")
            return False

    # ── Indeed ───────────────────────────────────────────────────────────────
    def _apply_indeed(self, job: JobListing, profile: CVProfile, creds: dict) -> bool:
        try:
            self.driver.get(job.url)
            time.sleep(3)
            apply_btn = WebDriverWait(self.driver, 8).until(
                EC.element_to_be_clickable((
                    By.XPATH,
                    "//button[contains(@class,'apply') or contains(text(),'Apply')]"
                ))
            )
            apply_btn.click()
            time.sleep(3)
            # Fill in email if prompted
            try:
                email_field = self.driver.find_element(By.ID, "emailInput")
                self._slow_type(email_field, profile.email)
                email_field.send_keys(Keys.RETURN)
                time.sleep(2)
            except NoSuchElementException:
                pass
            return True
        except Exception as e:
            log.debug(f"Indeed apply error: {e}")
            return False

    # ── LinkedIn ─────────────────────────────────────────────────────────────
    def _apply_linkedin(self, job: JobListing, profile: CVProfile, creds: dict) -> bool:
        try:
            # Login
            self.driver.get("https://www.linkedin.com/login")
            time.sleep(2)
            self._slow_type(self._wait(By.ID, "username"), creds.get("email", profile.email))
            self._slow_type(self.driver.find_element(By.ID, "password"), creds.get("password", ""))
            self.driver.find_element(By.XPATH, "//button[@type='submit']").click()
            time.sleep(4)
            self.driver.get(job.url)
            time.sleep(3)
            # Easy Apply
            easy_apply = WebDriverWait(self.driver, 8).until(
                EC.element_to_be_clickable((
                    By.XPATH,
                    "//button[contains(@class,'easy-apply') or contains(text(),'Easy Apply')]"
                ))
            )
            easy_apply.click()
            time.sleep(2)
            # Try to submit first modal step
            try:
                submit = self.driver.find_element(
                    By.XPATH, "//button[contains(text(),'Submit application')]"
                )
                submit.click()
                time.sleep(2)
            except NoSuchElementException:
                log.info("  Multi-step Easy Apply — manual completion needed")
            return True
        except Exception as e:
            log.debug(f"LinkedIn apply error: {e}")
            return False

    # ── Shine ────────────────────────────────────────────────────────────────
    def _apply_shine(self, job: JobListing, profile: CVProfile, creds: dict) -> bool:
        try:
            self.driver.get(job.url)
            time.sleep(3)
            apply_btn = WebDriverWait(self.driver, 8).until(
                EC.element_to_be_clickable((
                    By.XPATH, "//a[contains(text(),'Apply')] | //button[contains(text(),'Apply')]"
                ))
            )
            apply_btn.click()
            time.sleep(2)
            return True
        except Exception as e:
            log.debug(f"Shine apply error: {e}")
            return False


# ─────────────────────────────────────────────
# Step 5: Report Generator
# ─────────────────────────────────────────────
class ReportGenerator:
    DASHBOARD = "output/dashboard.html"
    ALL_JOBS  = "output/all_jobs.json"

    def save(self, jobs: list[JobListing], output_dir: str = "output"):
        Path(output_dir).mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        # ── Per-cycle JSON (for archiving) ──────────────────────────────
        json_path = f"{output_dir}/jobs_{ts}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump([asdict(j) for j in jobs], f, indent=2)

        # ── Rolling all_jobs.json (accumulates across cycles) ───────────
        all_jobs = []
        if Path(self.ALL_JOBS).exists():
            try:
                with open(self.ALL_JOBS, encoding="utf-8") as f:
                    all_jobs = json.load(f)
            except Exception:
                all_jobs = []
        existing_urls = {j["url"] for j in all_jobs}
        for j in jobs:
            d = asdict(j)
            if d["url"] not in existing_urls:
                all_jobs.append(d)
                existing_urls.add(d["url"])
            else:
                # Update existing entry (e.g. applied status may have changed)
                for idx, existing in enumerate(all_jobs):
                    if existing["url"] == d["url"]:
                        all_jobs[idx] = d
                        break
        with open(self.ALL_JOBS, "w", encoding="utf-8") as f:
            json.dump(all_jobs, f, indent=2, ensure_ascii=False)

        # ── Cover letter .txt files ──────────────────────────────────────
        cl_dir = f"{output_dir}/cover_letters_{ts}"
        Path(cl_dir).mkdir(exist_ok=True)
        for job in jobs:
            if job.cover_letter:
                safe = re.sub(r"[^\w\s-]", "", f"{job.company}_{job.title}")[:60]
                with open(f"{cl_dir}/{safe}.txt", "w", encoding="utf-8") as f:
                    f.write(f"Job: {job.title}\nCompany: {job.company}\nPortal: {job.portal}\n\n")
                    f.write(job.cover_letter)

        # ── HTML Dashboard (rolling, always up to date) ──────────────────
        self._write_dashboard(all_jobs)

        log.info(f"\n📁 Output saved:")
        log.info(f"   JSON        → {json_path}")
        log.info(f"   Dashboard   → {self.DASHBOARD}  ← open this in your browser!")
        log.info(f"   Cover letters → {cl_dir}/")
        return self.DASHBOARD, json_path

    def _write_dashboard(self, all_jobs: list[dict]):
        total      = len(all_jobs)
        applied    = sum(1 for j in all_jobs if j.get("applied"))
        pending    = total - applied
        portals    = {}
        for j in all_jobs:
            portals[j.get("portal","?")] = portals.get(j.get("portal","?"), 0) + 1

        portal_badges = "".join(
            f'<span class="badge">{p}: {c}</span>' for p, c in portals.items()
        )

        cards_html = ""
        for j in reversed(all_jobs):   # newest first
            status_cls  = "applied" if j.get("applied") else "pending"
            status_text = "✅ Applied" if j.get("applied") else "⏳ Pending"
            cl = j.get("cover_letter", "").strip()
            cl_block = (
                f'<div class="cl-toggle" onclick="this.nextElementSibling.classList.toggle(\'open\')">'
                f'📄 View Cover Letter</div>'
                f'<div class="cl-body"><pre>{cl}</pre></div>'
            ) if cl else '<p class="no-cl">No cover letter drafted.</p>'

            notes = j.get("notes", "")
            notes_html = f'<p class="notes">📝 {notes}</p>' if notes else ""

            applied_at = j.get("applied_at", "")
            applied_at_html = f'<p class="applied-at">Applied at: {applied_at}</p>' if applied_at else ""

            cards_html += f"""
<div class="card {status_cls}">
  <div class="card-header">
    <div>
      <span class="job-title">{j.get('title','')}</span>
      <span class="company">@ {j.get('company','')}</span>
    </div>
    <span class="status-badge {status_cls}">{status_text}</span>
  </div>
  <div class="meta">
    <span>🏢 {j.get('portal','')}</span>
    <span>📍 {j.get('location','')}</span>
    <span>⭐ Relevance: {j.get('relevance_score', 0):.0%}</span>
    <span>💰 {j.get('salary','') or 'Salary N/A'}</span>
  </div>
  <a class="job-url" href="{j.get('url','#')}" target="_blank">🔗 View Job Posting</a>
  {applied_at_html}
  {notes_html}
  {cl_block}
</div>"""

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Job Application Dashboard</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', sans-serif; background: #f0f4f8; color: #222; }}

  header {{
    background: linear-gradient(135deg, #1a1a2e, #16213e);
    color: white; padding: 28px 32px;
  }}
  header h1 {{ font-size: 1.8rem; margin-bottom: 6px; }}
  header p  {{ opacity: .7; font-size: .9rem; }}

  .stats {{
    display: flex; gap: 16px; flex-wrap: wrap;
    padding: 20px 32px; background: #fff;
    border-bottom: 1px solid #e0e0e0;
  }}
  .stat {{
    background: #f8f9ff; border-radius: 10px;
    padding: 14px 24px; text-align: center; min-width: 110px;
  }}
  .stat .num {{ font-size: 2rem; font-weight: 700; }}
  .stat .lbl {{ font-size: .75rem; color: #666; margin-top: 2px; }}
  .stat.green .num {{ color: #16a34a; }}
  .stat.blue  .num {{ color: #2563eb; }}
  .stat.amber .num {{ color: #d97706; }}

  .portal-row {{ padding: 12px 32px; background: #fff; border-bottom: 1px solid #eee; }}
  .badge {{
    display: inline-block; background: #e0e7ff; color: #3730a3;
    border-radius: 20px; padding: 3px 12px; font-size: .78rem;
    margin: 3px 4px 3px 0;
  }}

  .filters {{
    padding: 14px 32px; display: flex; gap: 10px; flex-wrap: wrap;
    background: #f0f4f8; border-bottom: 1px solid #ddd;
  }}
  .filters button {{
    border: 1px solid #cbd5e1; background: #fff; border-radius: 20px;
    padding: 5px 16px; cursor: pointer; font-size: .85rem; transition: all .2s;
  }}
  .filters button:hover, .filters button.active {{
    background: #1a1a2e; color: #fff; border-color: #1a1a2e;
  }}

  .cards {{ padding: 24px 32px; display: flex; flex-direction: column; gap: 16px; }}

  .card {{
    background: #fff; border-radius: 12px; padding: 20px 24px;
    box-shadow: 0 1px 4px rgba(0,0,0,.08);
    border-left: 5px solid #cbd5e1;
    transition: box-shadow .2s;
  }}
  .card:hover {{ box-shadow: 0 4px 16px rgba(0,0,0,.12); }}
  .card.applied {{ border-left-color: #16a34a; }}
  .card.pending  {{ border-left-color: #f59e0b; }}

  .card-header {{
    display: flex; justify-content: space-between;
    align-items: flex-start; gap: 12px; margin-bottom: 10px;
  }}
  .job-title {{ font-size: 1.1rem; font-weight: 700; }}
  .company   {{ font-size: .95rem; color: #555; margin-left: 6px; }}

  .status-badge {{
    font-size: .78rem; font-weight: 600; border-radius: 20px;
    padding: 4px 12px; white-space: nowrap;
  }}
  .status-badge.applied {{ background: #dcfce7; color: #15803d; }}
  .status-badge.pending  {{ background: #fef9c3; color: #92400e; }}

  .meta {{ display: flex; gap: 16px; flex-wrap: wrap; font-size: .82rem; color: #555; margin-bottom: 10px; }}
  .job-url {{ font-size: .83rem; color: #2563eb; text-decoration: none; }}
  .job-url:hover {{ text-decoration: underline; }}
  .applied-at {{ font-size: .78rem; color: #888; margin-top: 6px; }}
  .notes {{ font-size: .82rem; color: #b45309; margin-top: 6px; }}
  .no-cl {{ font-size: .8rem; color: #aaa; margin-top: 10px; }}

  .cl-toggle {{
    margin-top: 14px; cursor: pointer; font-size: .85rem;
    color: #2563eb; font-weight: 600; user-select: none;
  }}
  .cl-toggle:hover {{ text-decoration: underline; }}
  .cl-body {{ display: none; margin-top: 10px; }}
  .cl-body.open {{ display: block; }}
  .cl-body pre {{
    white-space: pre-wrap; font-family: 'Segoe UI', sans-serif;
    font-size: .85rem; line-height: 1.6; background: #f8fafc;
    border: 1px solid #e2e8f0; border-radius: 8px;
    padding: 16px; color: #334155;
  }}

  footer {{
    text-align: center; padding: 24px; font-size: .8rem; color: #999;
  }}
</style>
</head>
<body>

<header>
  <h1>📋 Job Application Dashboard</h1>
  <p>Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} &nbsp;|&nbsp; Refreshes each cycle automatically</p>
</header>

<div class="stats">
  <div class="stat blue">  <div class="num">{total}</div>   <div class="lbl">Total Jobs</div></div>
  <div class="stat green"> <div class="num">{applied}</div> <div class="lbl">Applied</div></div>
  <div class="stat amber"> <div class="num">{pending}</div> <div class="lbl">Pending</div></div>
</div>

<div class="portal-row"><strong>By portal:</strong> {portal_badges}</div>

<div class="filters">
  <strong style="line-height:2">Filter:</strong>
  <button class="active" onclick="filterCards('all', this)">All</button>
  <button onclick="filterCards('applied', this)">✅ Applied</button>
  <button onclick="filterCards('pending', this)">⏳ Pending</button>
</div>

<div class="cards" id="cards">
{cards_html}
</div>

<footer>Generated by Job Application Automator &nbsp;|&nbsp; {total} jobs tracked</footer>

<script>
function filterCards(type, btn) {{
  document.querySelectorAll('.filters button').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.querySelectorAll('.card').forEach(c => {{
    if (type === 'all') c.style.display = '';
    else c.style.display = c.classList.contains(type) ? '' : 'none';
  }});
}}
</script>
</body>
</html>"""

        with open(self.DASHBOARD, "w", encoding="utf-8") as f:
            f.write(html)
        log.info(f"   Dashboard updated → {self.DASHBOARD}")


# ─────────────────────────────────────────────
# Orchestrator
# ─────────────────────────────────────────────
class JobAutomator:
    PORTALS = {
        "naukri":    NaukriScraper,
        "indeed":    IndeedScraper,
        "linkedin":  LinkedInScraper,
        "shine":     ShineScraper,
        "monster":   MonsterScraper,
        "instahyre": InstahyreScraper,
    }

    def __init__(self):
        # Tracks URLs already seen/applied across cycles (persisted to disk)
        self.seen_urls: set[str] = set()
        self.seen_file = "output/seen_jobs.json"
        self._load_seen()

    def _load_seen(self):
        """Load previously seen job URLs from disk so we survive restarts."""
        Path("output").mkdir(exist_ok=True)
        if Path(self.seen_file).exists():
            try:
                with open(self.seen_file, encoding="utf-8") as f:
                    self.seen_urls = set(json.load(f))
                log.info(f"📂 Loaded {len(self.seen_urls)} previously seen jobs from disk")
            except Exception:
                self.seen_urls = set()

    def _save_seen(self):
        with open(self.seen_file, "w", encoding="utf-8") as f:
            json.dump(list(self.seen_urls), f, indent=2)

    def run_once(
        self,
        cv_profile,
        target_role: str,
        location: str,
        portals: list[str],
        max_jobs_per_portal: int,
        min_relevance: float,
        dry_run: bool,
        headless: bool,
        credentials: dict,
        skip_apply: bool,
        cycle: int,
    ) -> list[JobListing]:
        """Run a single search-and-apply cycle. Returns only NEW jobs processed."""

        log.info(f"\n{'=' * 60}")
        log.info(f"🔄 CYCLE #{cycle}  —  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log.info(f"{'=' * 60}")

        # 1. Search jobs across all portals
        all_jobs: list[JobListing] = []
        for portal_name in portals:
            scraper_cls = self.PORTALS.get(portal_name.lower())
            if scraper_cls:
                try:
                    jobs = scraper_cls().search(target_role, location, max_jobs_per_portal)
                    all_jobs.extend(jobs)
                except Exception as e:
                    log.warning(f"Portal {portal_name} error: {e}")

        # 2. Filter out already-seen jobs
        new_jobs = [j for j in all_jobs if j.url not in self.seen_urls]
        log.info(f"\n📊 Total fetched: {len(all_jobs)}  |  New (unseen): {len(new_jobs)}")

        if not new_jobs:
            log.info("  ✅ No new jobs this cycle — sleeping until next check.")
            return []

        # Mark all as seen immediately so parallel/rapid cycles don't duplicate
        for j in new_jobs:
            self.seen_urls.add(j.url)
        self._save_seen()

        # 3. Score & filter
        matcher = JobMatcher()
        relevant_jobs = matcher.score_and_filter(new_jobs, cv_profile, target_role, min_relevance)

        if not relevant_jobs:
            log.info("  No new jobs passed relevance filter this cycle.")
            return []

        # 4. Draft cover letters
        log.info(f"\n✍️  Drafting cover letters for {len(relevant_jobs)} new jobs...")
        for job in relevant_jobs:
            try:
                job.cover_letter = matcher.draft_cover_letter(job, cv_profile)
            except Exception as e:
                log.warning(f"Cover letter failed for {job.title}: {e}")

        # 5. Apply
        if not skip_apply:
            log.info(f"\n🚀 Applying to {len(relevant_jobs)} new jobs (dry_run={dry_run})...")
            applicator = SeleniumApplicator(headless=headless)
            relevant_jobs = applicator.apply_all(
                relevant_jobs, cv_profile, "",
                credentials, dry_run=dry_run
            )

        # 6. Append to rolling report
        ReportGenerator().save(relevant_jobs)
        applied_count = sum(1 for j in relevant_jobs if j.applied)
        log.info(f"\n✅ Cycle #{cycle} done — {applied_count}/{len(relevant_jobs)} applied.")
        return relevant_jobs

    def run_continuous(
        self,
        cv_path: str,
        target_role: str,
        location: str,
        portals: list[str] = None,
        max_jobs_per_portal: int = 10,
        min_relevance: float = 0.4,
        dry_run: bool = True,
        headless: bool = False,
        credentials: dict = None,
        skip_apply: bool = False,
        interval_minutes: int = 30,
    ):
        log.info("=" * 60)
        log.info("🤖 Job Application Automator — CONTINUOUS MODE")
        log.info(f"   Role     : {target_role}")
        log.info(f"   Location : {location}")
        log.info(f"   Interval : every {interval_minutes} minutes")
        log.info(f"   Dry run  : {dry_run}")
        log.info("   Press Ctrl+C to stop at any time.")
        log.info("=" * 60)

        portals = portals or list(self.PORTALS.keys())
        credentials = credentials or {}

        # Read CV once — reused every cycle
        log.info(f"\n📄 Reading CV: {cv_path}")
        cv_profile = CVReader().read(cv_path)
        log.info(f"✅ CV ready — {cv_profile.name} | {len(cv_profile.skills)} skills")

        cycle = 0
        total_applied = 0

        while True:
            cycle += 1
            try:
                new_jobs = self.run_once(
                    cv_profile=cv_profile,
                    target_role=target_role,
                    location=location,
                    portals=portals,
                    max_jobs_per_portal=max_jobs_per_portal,
                    min_relevance=min_relevance,
                    dry_run=dry_run,
                    headless=headless,
                    credentials=credentials,
                    skip_apply=skip_apply,
                    cycle=cycle,
                )
                total_applied += sum(1 for j in new_jobs if j.applied)
                log.info(f"   📈 Total applied so far (all cycles): {total_applied}")

            except KeyboardInterrupt:
                log.info("\n\n🛑 Stopped by user. Goodbye!")
                break
            except Exception as e:
                log.error(f"❌ Unexpected error in cycle #{cycle}: {e} — continuing after sleep.")

            # Sleep until next cycle, but wake up every 60s to stay responsive to Ctrl+C
            next_run = datetime.now().strftime('%H:%M:%S')
            wake_at = time.time() + interval_minutes * 60
            log.info(f"\n⏳ Next scan in {interval_minutes} min  (current time: {next_run})")
            try:
                while time.time() < wake_at:
                    time.sleep(60)
            except KeyboardInterrupt:
                log.info("\n\n🛑 Stopped by user. Goodbye!")
                break


# ─────────────────────────────────────────────
# CLI Entry Point
# ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Automated Job Application Tool (India) — Continuous Mode")
    parser.add_argument("--cv", required=True, help="Path to your CV PDF")
    parser.add_argument("--role", required=True, help="Target job role (e.g. 'Data Scientist')")
    parser.add_argument("--location", default="Bangalore", help="Preferred job location")
    parser.add_argument("--portals", nargs="+",
                        default=["naukri", "indeed", "linkedin", "shine", "monster", "instahyre"],
                        help="Portals to search: naukri indeed linkedin shine monster instahyre")
    parser.add_argument("--max-jobs", type=int, default=10, help="Max jobs per portal per cycle")
    parser.add_argument("--min-score", type=float, default=0.4, help="Minimum relevance score (0-1)")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Open browser only, don't submit (default: True)")
    parser.add_argument("--apply", action="store_true", help="Actually submit applications")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--skip-apply", action="store_true", help="Skip apply step entirely")
    parser.add_argument("--creds", default="credentials.json",
                        help="Path to credentials JSON file")
    parser.add_argument("--interval", type=int, default=30,
                        help="Minutes between each search cycle (default: 30)")
    args = parser.parse_args()

    # Load credentials
    credentials = {}
    if Path(args.creds).exists():
        with open(args.creds, encoding="utf-8") as f:
            credentials = json.load(f)
    else:
        log.warning(f"No credentials file found at {args.creds}. Login steps will be skipped.")

    dry_run = not args.apply

    JobAutomator().run_continuous(
        cv_path=args.cv,
        target_role=args.role,
        location=args.location,
        portals=args.portals,
        max_jobs_per_portal=args.max_jobs,
        min_relevance=args.min_score,
        dry_run=dry_run,
        headless=args.headless,
        credentials=credentials,
        skip_apply=args.skip_apply,
        interval_minutes=args.interval,
    )


if __name__ == "__main__":
    main()