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
    RECENCY_WEIGHT,
    RESUME_CLOUD,
    RESUME_KEYWORDS,
    RESUME_SKILLS,
    RESUME_TITLES,
    SKILLS_WEIGHT,
    TITLE_WEIGHT,
    load_env,
)
from job_tracker import filter_unseen, mark_recommended, seen_count

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


def _get_posted_at(job):
    """Return a human-readable posted date string, or empty string."""
    return (job.get("detected_extensions") or {}).get("posted_at") or ""


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


# --- Recency ---

def _recency_bonus(job):
    """
    Return a 0.0–1.0 recency factor based on the job's posted_at field.
    1.0 = posted within 24h, 0.0 = posted 1+ week ago.
    """
    posted = _get_posted_at(job).lower()
    if not posted:
        return 0.0

    if "just now" in posted or "today" in posted:
        return 1.0

    m = re.search(r"(\d+)\s*hour", posted)
    if m:
        return 1.0

    m = re.search(r"(\d+)\s*day", posted)
    if m:
        days = int(m.group(1))
        if days == 1:
            return 0.8
        if days == 2:
            return 0.6
        if days <= 3:
            return 0.4
        if days <= 7:
            return 0.2
        return 0.05  # "30+ days ago" still gets a tiny bump over no info

    m = re.search(r"(\d+)\s*week", posted)
    if m:
        return 0.1 if int(m.group(1)) == 1 else 0.0

    return 0.0


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
    """Compute a raw score for a single job. Base weights sum to 1.0; recency is an additive bonus."""
    text = _get_job_text(job)
    title = _get_job_title(job)

    base = (
        SKILLS_WEIGHT * _skills_score(text)
        + TITLE_WEIGHT * _title_score(title)
        + LOCATION_WEIGHT * _location_score(job, preferred_location)
        + KEYWORD_WEIGHT * _keyword_score(text)
    )
    return base + RECENCY_WEIGHT * _recency_bonus(job)


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
        posted = _get_posted_at(job)

        loc_display = location.title()
        if remote:
            loc_display += " (Remote)"

        title_html = f'<a href="{apply_url}">{title}</a>' if apply_url else title
        posted_html = f'<br/><span style="color:#27ae60; font-size:11px;">&#9679; {posted}</span>' if posted else ""
        bg = "#f9f9f9" if rank % 2 == 0 else "#ffffff"

        rows += f"""
        <tr style="background-color: {bg};">
            <td style="padding: 8px; text-align: center;">{rank}</td>
            <td style="padding: 8px; text-align: center; font-weight: bold;">{final}</td>
            <td style="padding: 8px;">{title_html}{posted_html}</td>
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
            &#9679; Green dot = recently posted (recency bonus applied).
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


def _offer_tailored_resumes(top_jobs):
    """After showing top jobs, ask if the user wants AI-tailored resumes for any."""
    try:
        from tailor_resume import generate_pdf, load_experience, tailor_with_claude
    except ImportError as e:
        print(f"\nResume tailoring unavailable (missing dependency): {e}")
        print("Run: pipenv install anthropic reportlab")
        return

    experience = load_experience()
    if not experience:
        return

    print("\nGenerate a tailored one-page resume for any of these jobs?")
    print("Enter rank(s) separated by commas (e.g. 1,3) or press Enter to skip:")
    choice = input("> ").strip()
    if not choice:
        return

    ranks = []
    for part in choice.split(","):
        part = part.strip()
        if part.isdigit() and 1 <= int(part) <= len(top_jobs):
            ranks.append(int(part))

    if not ranks:
        return

    for rank in ranks:
        job, _, _ = top_jobs[rank - 1]
        title = job.get("title") or "Unknown"
        company = _get_job_company(job)
        description = job.get("description") or ""

        if not description:
            print(f"  #{rank} {title} — no description available, skipping.")
            continue

        print(f"\n  Tailoring resume for #{rank}: {title} at {company}...")
        try:
            tailored = tailor_with_claude(experience, title, company, description)
            pdf_path = generate_pdf(experience, tailored, title, company)
            print(f"  Saved: {pdf_path}")
        except Exception as e:
            print(f"  Error generating resume: {e}")


def _select_scraper():
    """Prompt user to choose a scraper and return its fetch_jobs function."""
    print("Select scraper:")
    print("  1) SerpAPI / Google Jobs (requires SERPAPI_KEY, 100 free searches/month)")
    print("  2) JobSpy — LinkedIn, Indeed, Glassdoor, ZipRecruiter (free, no API key)")
    choice = input("Choice [1/2] (default: 2): ").strip()
    if choice == "1":
        from scraper import fetch_jobs
        return fetch_jobs
    else:
        from scraper_v2 import fetch_jobs
        return fetch_jobs


def main():
    load_env()

    fetch_jobs = _select_scraper()

    preferred = input("Enter preferred location (default: Chicago): ").strip()
    if not preferred:
        preferred = "Chicago"

    print(f"\nFetching jobs for '{preferred}' + Remote...")
    jobs = fetch_jobs(preferred)

    if not jobs:
        print("No jobs found.")
        return

    already_seen = seen_count()
    jobs = filter_unseen(jobs)
    print(f"Filtered out already-recommended jobs ({already_seen} in history). {len(jobs)} new jobs to score.")

    if not jobs:
        print("All fetched jobs have already been recommended. Try again tomorrow for fresh listings.")
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
        posted = _get_posted_at(job)

        loc_str = location.title()
        if remote:
            loc_str += " (Remote)"

        print(f"  #{rank}  Score: {final}/100  (raw: {raw:.3f})")
        print(f"      {title}")
        print(f"      {company} — {loc_str}")
        if posted:
            print(f"      Posted: {posted}")
        print(f"      Skills: {skills}")
        if url:
            print(f"      Apply: {url}")
        print()

    print("Sending email...")
    if send_email(top_10, preferred):
        sender = os.environ.get("GMAIL_ADDRESS")
        print(f"Email sent to {sender}")
        mark_recommended([job for job, _, _ in top_10])
        print(f"Recorded {len(top_10)} jobs to history (will not be recommended again).")
    else:
        print("Failed to send email. Results are printed above.")

    _offer_tailored_resumes(top_10)


if __name__ == "__main__":
    main()
