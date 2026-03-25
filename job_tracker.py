import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "seen_jobs.db"


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            company TEXT NOT NULL,
            recommended_on DATE NOT NULL,
            UNIQUE(title, company)
        )
    """)
    conn.commit()
    return conn


def filter_unseen(jobs):
    """Remove jobs that have already been recommended. Returns only new jobs."""
    conn = _connect()
    try:
        rows = conn.execute("SELECT title, company FROM seen_jobs").fetchall()
        seen = {(r[0], r[1]) for r in rows}
    finally:
        conn.close()

    return [
        job for job in jobs
        if (job.get("title", ""), job.get("company_name", "")) not in seen
    ]


def mark_recommended(jobs):
    """Record jobs as recommended so they are skipped in future runs."""
    from datetime import date
    conn = _connect()
    try:
        today = date.today().isoformat()
        conn.executemany(
            "INSERT OR IGNORE INTO seen_jobs (title, company, recommended_on) VALUES (?, ?, ?)",
            [(job.get("title", ""), job.get("company_name", ""), today) for job in jobs],
        )
        conn.commit()
    finally:
        conn.close()


def seen_count():
    """Return total number of jobs tracked in the database."""
    conn = _connect()
    try:
        return conn.execute("SELECT COUNT(*) FROM seen_jobs").fetchone()[0]
    finally:
        conn.close()
