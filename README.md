# 🎓 2027 New Grad Job Alert Bot — Setup Guide

> **Alerts sent to:** shruthib18122001@gmail.com  
> **Frequency:** Every hour via GitHub Actions  
> **Companies monitored:** Google, Meta, Apple, Amazon, Microsoft, OpenAI, Anthropic, xAI, Netflix, Stripe, Airbnb, Uber, DoorDash, Lyft, Databricks, Snowflake

---

## How It Works

```
Every Hour
    │
    ▼
GitHub Actions runs checker.py
    │
    ├─ Greenhouse API → OpenAI, Anthropic, Stripe, Airbnb, Databricks,
    │                   Snowflake, Lyft, DoorDash, Uber, Netflix
    ├─ Google Careers API
    ├─ Meta Careers GraphQL
    ├─ Apple Jobs API
    ├─ Amazon Jobs JSON
    ├─ Microsoft Careers API
    └─ xAI (Greenhouse)
    │
    ▼
Filter: title must contain new-grad + engineering keywords
    │
    ▼
Compare against seen_jobs.json (committed to repo)
    │
    ├─ New jobs found → Send HTML email to shruthib18122001@gmail.com
    │                    Commit updated seen_jobs.json
    └─ No new jobs   → Exit silently
```

---

## Step-by-Step Setup

### Step 1 — Create a Gmail App Password

> **Why?** Gmail requires an "App Password" (not your real password) for SMTP access.

1. Go to [myaccount.google.com/security](https://myaccount.google.com/security)
2. Under **"How you sign in to Google"**, click **2-Step Verification** and enable it
3. Back on the Security page, click **App passwords**
4. Select app: **Mail**, device: **Other**, type `Job Alert Bot` → click **Generate**
5. **Copy the 16-character password** — you'll need it in Step 3

---

### Step 2 — Push to GitHub

1. Create a **new private GitHub repository** at [github.com/new](https://github.com/new)
   - Name: `job-alert-bot` | Visibility: **Private** | Do NOT add README

2. Open a terminal and run:
   ```bash
   cd C:\Users\shrut\.gemini\antigravity-ide\scratch\job-alert-bot

   git init
   git add .
   git commit -m "feat: initial job alert bot"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/job-alert-bot.git
   git push -u origin main
   ```

---

### Step 3 — Add GitHub Secrets

Go to your repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| Secret Name      | Value                                         |
|------------------|-----------------------------------------------|
| `ALERT_EMAIL_TO` | `shruthib18122001@gmail.com`                  |
| `GMAIL_USER`     | `shruthib18122001@gmail.com`                  |
| `GMAIL_APP_PASS` | The 16-char App Password from Step 1          |

---

### Step 4 — Run It!

1. Go to your repo → **Actions** tab
2. Click **"2027 New Grad Job Alert"** → **Run workflow** (green button)
3. Watch the logs — companies are checked one by one
4. Check `shruthib18122001@gmail.com` for your first alert email!

The workflow then runs **automatically every hour** after that.

---

## Customization

### Add more companies (Greenhouse ATS)
Add to `GREENHOUSE_COMPANIES` in `checker.py`:
```python
"companytoken": "Company Name",
```
Find the token in their careers URL: `boards.greenhouse.io/TOKENHERE`

### Adjust keyword matching
```python
# Must match at least one (new-grad indicators)
NEW_GRAD_KEYWORDS = ["new grad", "2027", "campus", "entry level", ...]

# Must also match at least one (role type)
ROLE_KEYWORDS = ["software engineer", "ml engineer", "ai engineer", ...]
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| No email received | Check Actions logs; verify all 3 secrets are set |
| `SMTPAuthenticationError` | Re-generate Gmail App Password and update secret |
| Workflow not triggering | GitHub pauses crons on inactive repos — trigger manually first |
| Too many/few alerts | Adjust `NEW_GRAD_KEYWORDS` in `checker.py` |
