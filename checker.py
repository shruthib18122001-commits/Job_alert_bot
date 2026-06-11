#!/usr/bin/env python3
"""
New Grad Job Alert Bot — 2027 Graduates
Checks multiple company career pages/APIs and sends email alerts for new postings.
"""

import json
import os
import re
import smtplib
import sys
import time
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import requests

# Force UTF-8 output on Windows (avoids cp1252 UnicodeEncodeError)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

ALERT_EMAIL_TO   = os.environ.get("ALERT_EMAIL_TO", "shruthib18122001@gmail.com")
GMAIL_USER       = os.environ.get("GMAIL_USER", "shruthib18122001@gmail.com")
GMAIL_APP_PASS   = os.environ.get("GMAIL_APP_PASS", "")  # Gmail App Password

STATE_FILE       = Path("seen_jobs.json")
REQUEST_TIMEOUT  = 20  # seconds
RETRY_ATTEMPTS   = 3

# Keywords that indicate a new-grad / early-career role for 2027 graduates
NEW_GRAD_KEYWORDS = [
    "new grad", "new graduate", "university grad", "campus", "entry level",
    "early career", "university hire", "university recruit",
    "2027", "class of 2027", "undergraduate", "associate",
    "software engineer i ", " swe i", "junior swe", "junior software",
    "ai/ml engineer", "machine learning engineer", "ml engineer",
]

# Role type keywords (must match at least one of these)
ROLE_KEYWORDS = [
    "software engineer", "swe", "software developer",
    "machine learning", "ml engineer", "ai engineer",
    "artificial intelligence", "deep learning",
    "data engineer", "backend engineer", "frontend engineer",
    "full stack", "fullstack", "full-stack",
    "systems engineer", "platform engineer",
]

# ──────────────────────────────────────────────────────────────────────────────
# Company Sources
# ──────────────────────────────────────────────────────────────────────────────

# Greenhouse ATS — board token → company name
GREENHOUSE_COMPANIES = {
    "anthropic":   "Anthropic",
    "openai":      "OpenAI",
    "stripe":      "Stripe",
    "airbnb":      "Airbnb",
    "databricks":  "Databricks",
    "snowflake":   "Snowflake",
    "lyft":        "Lyft",
    "doordash":    "DoorDash",
    "uber":        "Uber",
    "netflix":     "Netflix",
}

# Lever ATS — site slug → company name  
LEVER_COMPANIES = {
    "openai":      "OpenAI",   # fallback if Greenhouse token differs
}

# Custom scrapers / unofficial JSON endpoints
# Each entry: (company_name, url, parser_function_name)
CUSTOM_SOURCES = [
    ("Google",     "google"),
    ("Meta",       "meta"),
    ("Apple",      "apple"),
    ("Amazon",     "amazon"),
    ("Microsoft",  "microsoft"),
    ("xAI",        "xai"),
]

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def _get(url: str, params: dict = None, json_mode: bool = True):
    """GET with retry logic."""
    for attempt in range(RETRY_ATTEMPTS):
        try:
            resp = requests.get(url, headers=HEADERS, params=params,
                                timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.json() if json_mode else resp.text
        except Exception as exc:
            if attempt == RETRY_ATTEMPTS - 1:
                print(f"  ✗ Failed {url}: {exc}")
                return None
            time.sleep(2 ** attempt)
    return None


def _matches_keywords(text: str) -> bool:
    """Return True if text looks like a new-grad engineering role."""
    low = text.lower()
    has_grad   = any(kw in low for kw in NEW_GRAD_KEYWORDS)
    has_role   = any(kw in low for kw in ROLE_KEYWORDS)
    return has_grad and has_role


def _matches_role_only(text: str) -> bool:
    """Looser check: just needs to be an engineering role (no grad filter)."""
    low = text.lower()
    return any(kw in low for kw in ROLE_KEYWORDS)


def load_seen() -> set:
    if STATE_FILE.exists():
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return set(data.get("seen", []))
    return set()


def save_seen(seen: set):
    STATE_FILE.write_text(
        json.dumps({"seen": sorted(seen), "updated": datetime.now(timezone.utc).isoformat()},
                   indent=2),
        encoding="utf-8",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Greenhouse Fetcher
# ──────────────────────────────────────────────────────────────────────────────

def fetch_greenhouse(board_token: str, company: str) -> list[dict]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"
    data = _get(url, params={"content": "false"})
    if not data:
        return []
    jobs = []
    for job in data.get("jobs", []):
        title    = job.get("title", "")
        job_id   = f"gh_{board_token}_{job.get('id', '')}"
        apply_url = job.get("absolute_url", "")
        location  = job.get("location", {}).get("name", "Remote")
        if _matches_keywords(title):
            jobs.append({
                "id":       job_id,
                "company":  company,
                "title":    title,
                "location": location,
                "url":      apply_url,
                "source":   "Greenhouse",
            })
    return jobs


# ──────────────────────────────────────────────────────────────────────────────
# Google Careers (unofficial JSON search endpoint)
# ──────────────────────────────────────────────────────────────────────────────

def fetch_google() -> list[dict]:
    """
    Google exposes a JSON search API used by careers.google.com.
    We query for 'new grad software engineer 2027'.
    """
    url = "https://careers.google.com/api/jobs/jobs-v1/search/"
    params = {
        "query":      "new grad software engineer",
        "location":   "",
        "distance":   50,
        "units":      "km",
        "employment_type": "FULL_TIME",
        "page_size":  20,
        "page":       1,
    }
    data = _get(url, params=params)
    if not data:
        return []
    jobs = []
    for job in data.get("jobs", []):
        title     = job.get("title", "")
        job_id    = f"google_{job.get('job_id', job.get('id', title))}"
        apply_url = "https://careers.google.com/jobs/results/" + str(job.get("job_id", ""))
        location  = ", ".join(job.get("locations", ["Various"]))
        if _matches_keywords(title):
            jobs.append({
                "id":       job_id,
                "company":  "Google",
                "title":    title,
                "location": location,
                "url":      apply_url,
                "source":   "Google Careers API",
            })
    return jobs


# ──────────────────────────────────────────────────────────────────────────────
# Meta Careers (unofficial search API)
# ──────────────────────────────────────────────────────────────────────────────

def fetch_meta() -> list[dict]:
    url = "https://www.metacareers.com/graphql"
    payload = {
        "operationName": "CareersJobSearchResultsQuery",
        "variables": {
            "search_input": {
                "q":          "new grad software engineer 2027",
                "divisions":  [],
                "offices":    [],
                "roles":      [],
                "leadership_levels": [],
                "teams":      [],
                "is_leadership": False,
                "page":       1,
                "results_per_page": 20,
            }
        },
        "doc_id": "10615630695416603",
    }
    try:
        resp = requests.post(url, json=payload, headers={
            **HEADERS, "Content-Type": "application/json"
        }, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        results = (data.get("data", {})
                       .get("job_search", {})
                       .get("results", []))
        jobs = []
        for job in results:
            title     = job.get("title", "")
            job_id    = f"meta_{job.get('id', title)}"
            apply_url = f"https://www.metacareers.com/jobs/{job.get('id', '')}"
            location  = job.get("sub_regions", ["Various"])[0] if job.get("sub_regions") else "Various"
            if _matches_keywords(title):
                jobs.append({
                    "id":       job_id,
                    "company":  "Meta",
                    "title":    title,
                    "location": location,
                    "url":      apply_url,
                    "source":   "Meta Careers",
                })
        return jobs
    except Exception as e:
        print(f"  ✗ Meta fetch failed: {e}")
        return []


# ──────────────────────────────────────────────────────────────────────────────
# Apple Jobs (RSS / JSON feed)
# ──────────────────────────────────────────────────────────────────────────────

def fetch_apple() -> list[dict]:
    url = "https://jobs.apple.com/api/role/search"
    payload = {
        "query":          "new grad software engineer",
        "filters":        {"postingpostLocation": [], "team": [], "product_line": []},
        "page":           1,
        "locale":         "en-us",
        "direction":      "DESC",
        "criteriaToFacetCount": 10,
    }
    try:
        resp = requests.post(url, json=payload, headers={
            **HEADERS, "Content-Type": "application/json"
        }, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        jobs = []
        for job in data.get("searchResults", []):
            title     = job.get("postingTitle", "")
            job_id    = f"apple_{job.get('positionId', title)}"
            apply_url = f"https://jobs.apple.com/en-us/details/{job.get('positionId', '')}"
            location  = job.get("location", {}).get("name", "Various")
            if _matches_keywords(title):
                jobs.append({
                    "id":       job_id,
                    "company":  "Apple",
                    "title":    title,
                    "location": location,
                    "url":      apply_url,
                    "source":   "Apple Jobs",
                })
        return jobs
    except Exception as e:
        print(f"  ✗ Apple fetch failed: {e}")
        return []


# ──────────────────────────────────────────────────────────────────────────────
# Amazon Jobs (AWS Jobs API)
# ──────────────────────────────────────────────────────────────────────────────

def fetch_amazon() -> list[dict]:
    url = "https://www.amazon.jobs/en/search.json"
    params = {
        "query":       "new grad software engineer 2027",
        "category[]":  ["software-development"],
        "normalized_country_code[]": ["USA"],
        "result_limit": 20,
        "offset":       0,
    }
    data = _get(url, params=params)
    if not data:
        return []
    jobs = []
    for job in data.get("jobs", []):
        title     = job.get("title", "")
        job_id    = f"amazon_{job.get('id_icims', job.get('job_id', title))}"
        apply_url = "https://www.amazon.jobs" + job.get("job_path", "")
        location  = job.get("normalized_location", "Various")
        if _matches_keywords(title):
            jobs.append({
                "id":       job_id,
                "company":  "Amazon",
                "title":    title,
                "location": location,
                "url":      apply_url,
                "source":   "Amazon Jobs",
            })
    return jobs


# ──────────────────────────────────────────────────────────────────────────────
# Microsoft Careers (unofficial API)
# ──────────────────────────────────────────────────────────────────────────────

def fetch_microsoft() -> list[dict]:
    url = "https://gcsservices.careers.microsoft.com/search/api/v1/search"
    params = {
        "q":         "new grad software engineer",
        "l":         "en_us",
        "pg":        1,
        "pgSz":      20,
        "o":         "Relevance",
        "flt":       True,
    }
    data = _get(url, params=params)
    if not data:
        return []
    jobs = []
    for job in data.get("operationResult", {}).get("result", {}).get("jobs", []):
        title     = job.get("title", "")
        job_id    = f"msft_{job.get('jobId', title)}"
        apply_url = f"https://careers.microsoft.com/us/en/job/{job.get('jobId', '')}"
        location  = job.get("primaryLocation", "Various")
        if _matches_keywords(title):
            jobs.append({
                "id":       job_id,
                "company":  "Microsoft",
                "title":    title,
                "location": location,
                "url":      apply_url,
                "source":   "Microsoft Careers",
            })
    return jobs


# ──────────────────────────────────────────────────────────────────────────────
# xAI Careers (Greenhouse)
# ──────────────────────────────────────────────────────────────────────────────

def fetch_xai() -> list[dict]:
    return fetch_greenhouse("xai", "xAI")


# ──────────────────────────────────────────────────────────────────────────────
# Aggregator
# ──────────────────────────────────────────────────────────────────────────────

CUSTOM_FETCHERS = {
    "google":    fetch_google,
    "meta":      fetch_meta,
    "apple":     fetch_apple,
    "amazon":    fetch_amazon,
    "microsoft": fetch_microsoft,
    "xai":       fetch_xai,
}


def fetch_all_jobs() -> list[dict]:
    all_jobs = []

    print("━━ Greenhouse companies ━━")
    for token, name in GREENHOUSE_COMPANIES.items():
        print(f"  Checking {name}…")
        jobs = fetch_greenhouse(token, name)
        print(f"    → {len(jobs)} matching job(s)")
        all_jobs.extend(jobs)

    print("━━ Custom sources ━━")
    for name, key in CUSTOM_SOURCES:
        fetcher = CUSTOM_FETCHERS.get(key)
        if not fetcher:
            continue
        print(f"  Checking {name}…")
        jobs = fetcher()
        print(f"    → {len(jobs)} matching job(s)")
        all_jobs.extend(jobs)

    return all_jobs


# ──────────────────────────────────────────────────────────────────────────────
# Email
# ──────────────────────────────────────────────────────────────────────────────

def build_email_html(new_jobs: list[dict]) -> str:
    now   = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    rows  = ""
    for job in new_jobs:
        rows += f"""
        <tr>
          <td style="padding:10px 8px;border-bottom:1px solid #2d2d3a;font-weight:600;color:#e2e8f0">{job['company']}</td>
          <td style="padding:10px 8px;border-bottom:1px solid #2d2d3a;color:#a5b4fc">
            <a href="{job['url']}" style="color:#818cf8;text-decoration:none">{job['title']}</a>
          </td>
          <td style="padding:10px 8px;border-bottom:1px solid #2d2d3a;color:#94a3b8;font-size:13px">{job['location']}</td>
          <td style="padding:10px 8px;border-bottom:1px solid #2d2d3a">
            <a href="{job['url']}" style="
              background:#6366f1;color:#fff;padding:5px 14px;border-radius:6px;
              text-decoration:none;font-size:13px;font-weight:600
            ">Apply →</a>
          </td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#0f0f1a;font-family:'Segoe UI',Arial,sans-serif">
  <div style="max-width:720px;margin:32px auto;background:#1a1a2e;border-radius:16px;overflow:hidden;box-shadow:0 8px 32px rgba(0,0,0,.4)">
    <!-- Header -->
    <div style="background:linear-gradient(135deg,#6366f1,#8b5cf6,#a855f7);padding:32px 36px">
      <div style="font-size:11px;letter-spacing:3px;text-transform:uppercase;color:#e0d7ff;margin-bottom:8px">🎓 2027 New Grad Alert</div>
      <h1 style="margin:0;font-size:26px;font-weight:700;color:#fff">
        {len(new_jobs)} New Job{' ' if len(new_jobs)==1 else 's '}Found!
      </h1>
      <p style="margin:8px 0 0;color:#c4b5fd;font-size:14px">Detected at {now}</p>
    </div>

    <!-- Table -->
    <div style="padding:28px 24px">
      <table style="width:100%;border-collapse:collapse">
        <thead>
          <tr style="background:#12122a">
            <th style="padding:10px 8px;text-align:left;font-size:11px;letter-spacing:1px;color:#6b7280;text-transform:uppercase">Company</th>
            <th style="padding:10px 8px;text-align:left;font-size:11px;letter-spacing:1px;color:#6b7280;text-transform:uppercase">Role</th>
            <th style="padding:10px 8px;text-align:left;font-size:11px;letter-spacing:1px;color:#6b7280;text-transform:uppercase">Location</th>
            <th style="padding:10px 8px;text-align:left;font-size:11px;letter-spacing:1px;color:#6b7280;text-transform:uppercase">Link</th>
          </tr>
        </thead>
        <tbody>
          {rows}
        </tbody>
      </table>
    </div>

    <!-- Footer -->
    <div style="padding:20px 36px;border-top:1px solid #2d2d3a;background:#12122a">
      <p style="margin:0;font-size:12px;color:#4b5563">
        🤖 Monitored via GitHub Actions · Runs every hour<br>
        Companies: Google, Meta, Apple, Amazon, Microsoft, OpenAI, Anthropic, xAI,
        Netflix, Stripe, Airbnb, Uber, DoorDash, Lyft, Databricks, Snowflake
      </p>
    </div>
  </div>
</body>
</html>"""


def send_email(new_jobs: list[dict]):
    if not GMAIL_APP_PASS:
        print("⚠  GMAIL_APP_PASS not set — skipping email.")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🚨 {len(new_jobs)} New 2027 Grad Role(s) Found!"
    msg["From"]    = GMAIL_USER
    msg["To"]      = ALERT_EMAIL_TO

    plain = "\n".join(
        f"{j['company']} | {j['title']} | {j['location']}\n{j['url']}"
        for j in new_jobs
    )
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(build_email_html(new_jobs), "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(GMAIL_USER, GMAIL_APP_PASS)
        smtp.sendmail(GMAIL_USER, ALERT_EMAIL_TO, msg.as_string())
    print(f"✅ Email sent to {ALERT_EMAIL_TO}")


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*60}")
    print(f"  2027 New Grad Job Alert Bot — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*60}\n")

    seen = load_seen()
    print(f"Loaded {len(seen)} previously seen job IDs.\n")

    all_jobs = fetch_all_jobs()
    print(f"\nTotal matching jobs found: {len(all_jobs)}")

    new_jobs = [j for j in all_jobs if j["id"] not in seen]
    print(f"New (unseen) jobs: {len(new_jobs)}")

    if new_jobs:
        print("\n📋 New jobs:")
        for j in new_jobs:
            print(f"  [{j['company']}] {j['title']} — {j['location']}")
            print(f"    {j['url']}")

        send_email(new_jobs)

        # Update seen set
        seen.update(j["id"] for j in new_jobs)
    else:
        print("No new jobs since last check.")

    save_seen(seen)
    print("\nDone. seen_jobs.json updated.\n")


if __name__ == "__main__":
    main()
