# Hiring Matcher

A Python CLI tool that scrapes job postings from Google Jobs, scores them against your resume, and emails you the top 10 matches daily.

## How It Works

1. Fetches jobs from Google Jobs via [SerpAPI](https://serpapi.com) using multiple search queries (location-specific + remote)
2. Scores each job against your resume using a weighted multi-factor algorithm:
   - **Skills match (45%)** — tech skills from your resume found in the job listing
   - **Title match (25%)** — how closely the job title matches titles you've held
   - **Location match (15%)** — bonus for remote, preferred city, or Chicago-based roles
   - **Keyword match (15%)** — domain keywords (e.g. "data pipeline", "full-stack", "cloud")
3. Normalizes scores to 0–100 using z-score + CDF mapping for a bell curve distribution
4. Prints the top 10 to your terminal and sends a formatted HTML email

## Prerequisites

- Python 3.8+
- [pipenv](https://pipenv.pypa.io/en/latest/)
- A free [SerpAPI](https://serpapi.com) account (100 searches/month on the free tier)
- A Gmail account with an [App Password](https://myaccount.google.com/apppasswords) for sending emails

## Setup

```bash
# Clone the repo
git clone https://github.com/dgv98/hiring-matcher.git
cd hiring-matcher

# Install dependencies
pipenv install

# Create your .env file
cp .env.example .env
```

Edit `.env` with your credentials:

```
GMAIL_ADDRESS=you@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
SERPAPI_KEY=your_serpapi_key_here
```

### Getting API Keys

**SerpAPI Key:**
1. Sign up at [serpapi.com](https://serpapi.com) (free tier, no credit card required)
2. Copy your API key from the [dashboard](https://serpapi.com/manage-api-key)

**Gmail App Password:**
1. Enable 2-Step Verification on your Google account
2. Go to [App Passwords](https://myaccount.google.com/apppasswords)
3. Generate a new app password for "Mail"
4. Copy the 16-character password (spaces are fine)

## Usage

### Load your resume

Before your first run, parse your resume PDF to populate the scoring config:

```bash
# Auto-detects the first .pdf in the project directory
pipenv run python update_resume.py

# Or specify a path
pipenv run python update_resume.py /path/to/your/resume.pdf
```

This extracts your skills, job titles, and keywords from the PDF and writes them to `config.py`. You'll see a preview of what was found and can confirm before saving.

### Run the job matcher

```bash
pipenv run python main.py
```

You'll be prompted for a preferred location (defaults to Chicago). The script searches for jobs in that location plus remote positions, scores them, prints the top 10, and sends an email.

### Update your resume

Whenever you update your resume, re-run the parser:

```bash
pipenv run python update_resume.py new_resume.pdf
```

## Project Structure

```
hiring_matcher/
├── main.py              # CLI entry point, scoring, normalization, email
├── scraper.py           # Google Jobs fetching via SerpAPI
├── config.py            # Resume data, scoring weights (auto-generated)
├── update_resume.py     # PDF resume parser, updates config.py
├── Pipfile              # Python dependencies
├── .env                 # API keys and credentials (not committed)
├── .env.example         # Template for .env
├── .gitignore
└── README.md
```

## Configuration

### Scoring Weights

Edit `config.py` to adjust how much each factor matters:

```python
SKILLS_WEIGHT = 0.45    # Technical skills match
TITLE_WEIGHT = 0.25     # Job title similarity
LOCATION_WEIGHT = 0.15  # Location/remote preference
KEYWORD_WEIGHT = 0.15   # Domain keyword overlap
```

Weights must sum to 1.0.

### Search Queries

Edit the query lists in `scraper.py` to customize what jobs are fetched:

```python
LOCATION_QUERIES = [
    "software developer jobs in {location}",
    "software engineer jobs in {location}",
    # Add more...
]

REMOTE_QUERIES = [
    "remote software developer jobs",
    "remote cloud engineer jobs",
    # Add more...
]
```

Each query uses one SerpAPI search credit per page. The free tier allows 100 searches/month.

### Skills Dictionary

The resume parser (`update_resume.py`) matches against a built-in dictionary of 150+ tech skills. To add skills that aren't recognized, edit the `KNOWN_SKILLS` set in `update_resume.py`, or manually add them to `config.py`.

## Contributing

Contributions are welcome! Here's how to get started:

### Reporting Issues

- Use [GitHub Issues](https://github.com/dgv98/hiring-matcher/issues) to report bugs or request features
- Include your Python version, OS, and any error output
- For scraping issues, note whether the SerpAPI response structure may have changed

### Development Setup

```bash
git clone https://github.com/dgv98/hiring-matcher.git
cd hiring-matcher
pipenv install --dev
```

### Contribution Guidelines

1. **Fork the repo** and create a feature branch from `main`
2. **Keep changes focused** — one feature or fix per PR
3. **Follow existing code style** — the project uses standard Python conventions
4. **Test your changes** — run the script end-to-end before submitting
5. **Update documentation** — if you add a feature, update this README

### Areas for Contribution

- **New job sources** — add scrapers for other job boards (Indeed, LinkedIn, etc.) alongside SerpAPI
- **Improved scoring** — better NLP-based matching, semantic similarity, or ML-based scoring
- **Resume parsing** — improve skill extraction accuracy, support more file formats (DOCX, plain text)
- **Scheduling** — add built-in cron/scheduler support for automated daily runs
- **Notification channels** — Slack, Discord, or SMS alerts in addition to email
- **UI/Dashboard** — a web interface to view results and configure preferences
- **Test coverage** — unit tests for scoring logic, scraper response parsing, and resume extraction

### Pull Request Process

1. Fork and clone the repository
2. Create a branch: `git checkout -b feature/your-feature`
3. Make your changes and test them
4. Commit with a clear message describing what and why
5. Push and open a pull request against `main`
6. Describe your changes in the PR description

## License

MIT

## Acknowledgments

- [SerpAPI](https://serpapi.com) for Google Jobs access
- [PyMuPDF](https://pymupdf.readthedocs.io/) for PDF text extraction
