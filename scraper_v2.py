"""
Scraper v2 — uses python-jobspy (free, no API key required).
Scrapes LinkedIn, Indeed, Glassdoor, and ZipRecruiter simultaneously.
Normalizes output to the same dict format as scraper.py so main.py works unchanged.
"""
import math
from datetime import date

SEARCH_TERMS = [
    "quantum software engineer",
    "quantum computing engineer",
    "quantum software developer",
]


def _days_ago_str(job_date):
    """Convert a date object to a human-readable 'X days ago' string."""
    if not job_date or (hasattr(job_date, '__class__') and job_date.__class__.__name__ == 'NaTType'):
        return ""
    try:
        delta = (date.today() - job_date).days
    except Exception:
        return ""

    if delta == 0:
        return "today"
    if delta == 1:
        return "1 day ago"
    if delta < 7:
        return f"{delta} days ago"
    weeks = delta // 7
    return f"{weeks} week{'s' if weeks > 1 else ''} ago"


def _normalize(row):
    """Convert a jobspy DataFrame row to the dict format main.py expects."""
    # Handle NaN/NaT safely
    def safe(val, default=""):
        if val is None:
            return default
        try:
            if isinstance(val, float) and math.isnan(val):
                return default
        except (TypeError, ValueError):
            pass
        return val

    job_url = safe(row.get("job_url")) or safe(row.get("job_url_direct"))
    is_remote = bool(safe(row.get("is_remote"), False))
    date_posted = row.get("date_posted")
    posted_str = _days_ago_str(date_posted)

    return {
        "title": safe(row.get("title")),
        "company_name": safe(row.get("company")),
        "location": safe(row.get("location")),
        "description": safe(row.get("description")),
        "apply_options": [{"link": job_url}] if job_url else [],
        "job_highlights": [],
        "detected_extensions": {
            "posted_at": posted_str,
            "work_from_home": is_remote,
        },
    }


def fetch_jobs(location_name, results_per_search=50):
    """
    Fetch jobs using python-jobspy. Searches multiple terms for both
    the preferred location and remote. Returns a deduplicated list of
    normalized job dicts compatible with main.py.
    """
    try:
        from jobspy import scrape_jobs
    except ImportError:
        print("Error: python-jobspy is not installed.")
        print("Run: pipenv install python-jobspy")
        return []

    all_jobs = []
    seen = set()

    sites = ["linkedin", "indeed", "glassdoor", "zip_recruiter"]

    for term in SEARCH_TERMS:
        for is_remote, loc in [(False, location_name), (True, "")]:
            label = f"{'remote ' if is_remote else ''}{term}{' in ' + location_name if not is_remote else ''}"
            print(f"Searching: {label}")
            try:
                df = scrape_jobs(
                    site_name=sites,
                    search_term=term,
                    location=loc if not is_remote else None,
                    results_wanted=results_per_search,
                    is_remote=is_remote if is_remote else None,
                    country_indeed="USA",
                )
            except Exception as e:
                print(f"  Error: {e}")
                continue

            new = 0
            for _, row in df.iterrows():
                key = (row.get("title", ""), row.get("company", ""))
                if key not in seen:
                    seen.add(key)
                    all_jobs.append(_normalize(row.to_dict()))
                    new += 1
            print(f"  {len(df)} results, {new} new ({len(all_jobs)} total)")

    return all_jobs
