import os
import re
import smtplib
import statistics
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import (
    KEYWORD_WEIGHT,
    LOCATION_WEIGHT,
    RESUME_CLOUD,
    RESUME_KEYWORDS,
    RESUME_SKILLS,
    RESUME_TITLES,
    SKILLS_WEIGHT,
    TITLE_WEIGHT,
    load_env,
)
from scraper import fetch_jobs

# Pre-compile word-boundary patterns for short skill names to avoid false positives
_SKILL_PATTERNS = {}
for skill in RESUME_SKILLS | RESUME_CLOUD:
    if len(skill) <= 3:
        _SKILL_PATTERNS[skill] = re.compile(rf"\b{re.escape(skill)}\b", re.IGNORECASE)
    else:
        _SKILL_PATTERNS[skill] = re.compile(re.escape(skill), re.IGNORECASE)


# --- Field accessors for Google Jobs (SerpAPI) format ---

def _get_job_text(job):
    """Extract searchable text from a job dict."""
    parts = []
    for key in ("title", "description"):
        val = job.get(key)
        if val and isinstance(val, str):
            parts.append(val)
    # Google Jobs nests highlights with qualifications/responsibilities
    for section in job.get("job_highlights", []):
        for item in section.get("items", []):
            parts.append(item)
    return " ".join(parts).lower()


def _get_job_title(job):
    return (job.get("title") or "").lower()


def _get_job_location(job):
    return (job.get("location") or "").lower()


def _get_job_company(job):
    return job.get("company_name") or ""


def _get_apply_url(job):
    # SerpAPI provides apply_options with links
    opts = job.get("apply_options", [])
    if opts:
        return opts[0].get("link", "")
    return job.get("share_link") or job.get("related_links", [{}])[0].get("link", "") if job.get("related_links") else ""


def _is_remote(job):
    """Check if job is remote."""
    title = _get_job_title(job)
    location = _get_job_location(job)
    text = f"{title} {location}"
    # Google Jobs sometimes includes work-from-home extensions
    extensions = job.get("detected_extensions", {})
    if extensions.get("work_from_home"):
        return True
    if "remote" in text:
        return True
    return False


# --- Scoring functions ---

def _skills_score(text):
    """Score based on how many resume skills appear in the job text."""
    all_skills = RESUME_SKILLS | RESUME_CLOUD
    matched = sum(1 for skill, pat in _SKILL_PATTERNS.items() if pat.search(text))
    return matched / len(all_skills)


def _title_score(job_title):
    """Score based on how well the job title matches resume titles."""
    if not job_title:
        return 0.0

    for title in RESUME_TITLES:
        if title in job_title:
            return 1.0

    job_words = set(job_title.split())
    best = 0.0
    for title in RESUME_TITLES:
        title_words = set(title.split())
        if title_words:
            overlap = len(job_words & title_words) / len(title_words)
            best = max(best, overlap)
    return best


def _location_score(job, preferred_location):
    """Score based on location match."""
    location = _get_job_location(job)
    preferred = preferred_location.lower()
    remote = _is_remote(job)

    if remote:
        return 1.0
    if preferred in location:
        return 1.0
    if "chicago" in location:
        return 0.9
    return 0.0


def _keyword_score(text):
    """Score based on resume keyword matches in job text."""
    matched = sum(1 for kw in RESUME_KEYWORDS if kw in text)
    return matched / len(RESUME_KEYWORDS)


def score_job(job, preferred_location):
    """Compute a raw score (0.0-1.0) for a single job."""
    text = _get_job_text(job)
    title = _get_job_title(job)

    return (
        SKILLS_WEIGHT * _skills_score(text)
        + TITLE_WEIGHT * _title_score(title)
        + LOCATION_WEIGHT * _location_score(job, preferred_location)
        + KEYWORD_WEIGHT * _keyword_score(text)
    )


def _matched_skills(job):
    """Return list of resume skills found in this job."""
    text = _get_job_text(job)
    return [skill for skill, pat in _SKILL_PATTERNS.items() if pat.search(text)]


def normalize_scores(scored_jobs):
    """
    Apply z-score normalization with CDF mapping to get 0-100 scores
    with approximately normal distribution.
    """
    if not scored_jobs:
        return []

    raw_scores = [s for _, s in scored_jobs]

    if len(raw_scores) < 2 or statistics.stdev(raw_scores) == 0:
        max_raw = max(raw_scores) if raw_scores else 1
        return [
            (job, raw, int((raw / max_raw) * 100) if max_raw > 0 else 50)
            for job, raw in scored_jobs
        ]

    mean = statistics.mean(raw_scores)
    stdev = statistics.stdev(raw_scores)
    norm_dist = statistics.NormalDist()

    results = []
    for job, raw in scored_jobs:
        z = (raw - mean) / stdev
        final = int(norm_dist.cdf(z) * 100)
        final = max(0, min(100, final))
        results.append((job, raw, final))

    results.sort(key=lambda x: x[2], reverse=True)
    return results


def build_html_email(top_jobs, preferred_location):
    """Build an HTML email body for the top job matches."""
    rows = ""
    for rank, (job, raw, final) in enumerate(top_jobs, 1):
        title = job.get("title") or "Unknown"
        company = _get_job_company(job)
        location = _get_job_location(job) or "N/A"
        apply_url = _get_apply_url(job)
        skills = ", ".join(sorted(_matched_skills(job)))
        remote = _is_remote(job)

        loc_display = location.title()
        if remote:
            loc_display += " (Remote)"

        title_html = f'<a href="{apply_url}">{title}</a>' if apply_url else title
        bg = "#f9f9f9" if rank % 2 == 0 else "#ffffff"

        rows += f"""
        <tr style="background-color: {bg};">
            <td style="padding: 8px; text-align: center;">{rank}</td>
            <td style="padding: 8px; text-align: center; font-weight: bold;">{final}</td>
            <td style="padding: 8px;">{title_html}</td>
            <td style="padding: 8px;">{company}</td>
            <td style="padding: 8px;">{loc_display}</td>
            <td style="padding: 8px; font-size: 12px;">{skills}</td>
        </tr>"""

    return f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 900px; margin: auto;">
        <h2>Top 10 Job Matches &mdash; {date.today().strftime('%B %d, %Y')}</h2>
        <p>Preferred location: <strong>{preferred_location}</strong> (+ Remote)</p>
        <table style="border-collapse: collapse; width: 100%;" border="1" cellpadding="0" cellspacing="0">
            <tr style="background-color: #333; color: #fff;">
                <th style="padding: 8px;">Rank</th>
                <th style="padding: 8px;">Score</th>
                <th style="padding: 8px;">Job Title</th>
                <th style="padding: 8px;">Company</th>
                <th style="padding: 8px;">Location</th>
                <th style="padding: 8px;">Matching Skills</th>
            </tr>
            {rows}
        </table>
        <p style="color: #888; font-size: 12px; margin-top: 16px;">
            Score is normalized (0-100) across all fetched jobs. Higher = better match to your resume.
        </p>
    </body>
    </html>
    """


def send_email(top_jobs, preferred_location):
    """Send the top matches email via Gmail SMTP."""
    sender = os.environ.get("GMAIL_ADDRESS")
    password = os.environ.get("GMAIL_APP_PASSWORD")

    if not sender or not password:
        print("Error: GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set in .env")
        return False

    html = build_html_email(top_jobs, preferred_location)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Top 10 Job Matches - {date.today()}"
    msg["From"] = sender
    msg["To"] = sender
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender, password)
            server.sendmail(sender, sender, msg.as_string())
        return True
    except Exception as e:
        print(f"Email error: {e}")
        return False


def main():
    load_env()

    preferred = input("Enter preferred location (default: Chicago): ").strip()
    if not preferred:
        preferred = "Chicago"

    print(f"\nFetching jobs for '{preferred}' + Remote...")
    jobs = fetch_jobs(preferred)

    if not jobs:
        print("No jobs found. Check your SERPAPI_KEY in .env.")
        return

    print(f"\nScoring {len(jobs)} jobs against your resume...")

    scored = [(job, score_job(job, preferred)) for job in jobs]
    normalized = normalize_scores(scored)
    top_10 = normalized[:10]

    print(f"\n{'='*80}")
    print(f"  TOP 10 JOB MATCHES — {date.today()}")
    print(f"{'='*80}\n")

    for rank, (job, raw, final) in enumerate(top_10, 1):
        title = job.get("title") or "Unknown"
        company = _get_job_company(job)
        location = _get_job_location(job) or "N/A"
        remote = _is_remote(job)
        skills = ", ".join(sorted(_matched_skills(job)))
        url = _get_apply_url(job)

        loc_str = location.title()
        if remote:
            loc_str += " (Remote)"

        print(f"  #{rank}  Score: {final}/100  (raw: {raw:.3f})")
        print(f"      {title}")
        print(f"      {company} — {loc_str}")
        print(f"      Skills: {skills}")
        if url:
            print(f"      Apply: {url}")
        print()

    print("Sending email...")
    if send_email(top_10, preferred):
        sender = os.environ.get("GMAIL_ADDRESS")
        print(f"Email sent to {sender}")
    else:
        print("Failed to send email. Results are printed above.")


if __name__ == "__main__":
    main()
