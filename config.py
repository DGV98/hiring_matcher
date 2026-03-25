import os

# --- Resume Data (structured for reliable scoring) ---

RESUME_SKILLS = {
    "c",
    "chakra ui",
    "ci/cd",
    "css",
    "django",
    "flask",
    "flutter",
    "github actions",
    "heroku",
    "html",
    "javascript",
    "kanban",
    "pick basic",
    "python",
    "qiskit",
    "r",
    "react",
    "rest api",
    "sql",
    "supabase",
    "terraform",
    "typescript",
    "vercel",
}

RESUME_CLOUD = {
    "aws",
    "azure",
    "gcp",
}

RESUME_TITLES = [
    "software developer",
    "software engineer",
    "senior software engineer",
    "research assistant",
]

RESUME_KEYWORDS = {
    "api",
    "cloud",
    "data pipeline",
    "facial recognition",
    "front end",
    "full-stack",
    "monitoring",
    "pose estimation",
    "quantum",
    "rest api",
}

# --- Scoring Weights ---
# Note: weights below sum to 1.0. RECENCY_WEIGHT is an additive bonus (max +0.10).

SKILLS_WEIGHT = 0.45
TITLE_WEIGHT = 0.25
LOCATION_WEIGHT = 0.15
KEYWORD_WEIGHT = 0.15
RECENCY_WEIGHT = 0.10  # Bonus for recently posted jobs (0 = week+ old, 1 = <24h)


def load_env():
    """Load .env file into os.environ."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())
