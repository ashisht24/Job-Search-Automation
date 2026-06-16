# 🤖 Job Application Automator — India

Automates job searching, cover letter generation, and applications across major Indian job portals using AI, Python  and Selenium.

---

## 🗂️ Files

```
job_apply/
├── job_automator.py      # Main script
├── credentials.json      # Your login credentials (never commit this!)
├── .env                  # API keys
├── requirements.txt      # Python dependencies
└── output/               # Generated reports & cover letters (auto-created)
```

---

## ✅ Supported Portals

| Portal | Search | Auto-Apply |
|---|---|---|
| **Naukri.com** | ✅ | ✅ (login required) |
| **LinkedIn** | ✅ | ✅ Easy Apply |
| **Indeed India** | ✅ | ✅ (partial) |
| **Shine.com** | ✅ | ✅ (login required) |
| **Monster India** | ✅ | ⚠️ Opens page |
| **Instahyre** | ✅ (URL) | ⚠️ Opens page |

> ⚠️ Auto-apply may break as portals update their HTML. The script opens the browser visibly so you can intervene.

---

## 🚀 Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Set your Anthropic API key
Edit `.env`:
```
ANTHROPIC_API_KEY=sk-ant-...
```
Get your key at https://console.anthropic.com

### 3. Add your login credentials
Edit `credentials.json` with your portal logins.

---

## 💻 Usage

### Dry run (search + cover letters, browser opens but doesn't submit)
```bash
python job_automator.py \
  --cv /path/to/your_cv.pdf \
  --role "Data Scientist" \
  --location "Bangalore"
```

### Search specific portals only
```bash
python job_automator.py \
  --cv cv.pdf \
  --role "Software Engineer" \
  --location "Mumbai" \
  --portals naukri linkedin indeed
```

### Actually apply (Selenium submits)
```bash
python job_automator.py \
  --cv cv.pdf \
  --role "Product Manager" \
  --location "Hyderabad" \
  --apply
```

### Skip apply step (just search + cover letters)
```bash
python job_automator.py \
  --cv cv.pdf \
  --role "ML Engineer" \
  --location "Pune" \
  --skip-apply
```

### Run headless (no visible browser window)
```bash
python job_automator.py --cv cv.pdf --role "DevOps Engineer" --apply --headless
```

---

## ⚙️ All Options

| Flag | Default | Description |
|---|---|---|
| `--cv` | required | Path to your PDF CV |
| `--role` | required | Target job title |
| `--location` | Bangalore | Preferred city |
| `--portals` | all 6 | Space-separated portal names |
| `--max-jobs` | 10 | Max jobs to fetch per portal |
| `--min-score` | 0.4 | Relevance threshold (0.0–1.0) |
| `--apply` | False | Submit applications (default is dry-run) |
| `--headless` | False | Hide browser window |
| `--skip-apply` | False | Only search + generate cover letters |
| `--creds` | credentials.json | Path to credentials file |

---

## 📁 Output

After each run, an `output/` folder is created with:

```
output/
├── report_20240615_143020.md          # Human-readable summary
├── jobs_20240615_143020.json          # Machine-readable job data
└── cover_letters_20240615_143020/
    ├── Google_Software_Engineer.txt
    ├── Flipkart_Data_Scientist.txt
    └── ...
```

---

## ⚠️ Important Notes

1. **Portals actively block automation.** LinkedIn and Naukri especially add CAPTCHAs and bot detection. Run without `--headless` so you can solve them manually.

2. **Easy Apply on LinkedIn works best** — it's officially designed for quick applications and is more automation-friendly.

3. **Terms of Service** — automated scraping may violate some portals' ToS. Use responsibly and throttle requests (the script adds random delays automatically).

4. **Keep `credentials.json` private** — add it to `.gitignore` if using git.

5. **Scanned CVs won't work** — your PDF must have a text layer. If it's scanned, use Adobe Acrobat or an OCR tool first.

---

## 🔧 Extending

To add a new portal, create a class following this pattern:

```python
class NewPortalScraper:
    def search(self, role: str, location: str, max_jobs: int) -> list[JobListing]:
        ...
```

Then register it in `JobAutomator.PORTALS`.
