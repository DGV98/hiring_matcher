"""
Extract skills, titles, and keywords from a resume PDF and update config.py.

Usage: pipenv run python update_resume.py [path/to/resume.pdf]
       Defaults to the first .pdf file in the project directory.
"""

import os
import re
import sys

import fitz  # PyMuPDF

# Comprehensive list of tech skills to match against resume text.
# Grouped by category for maintainability — all get flattened for matching.
KNOWN_SKILLS = {
    # Languages
    "python", "javascript", "typescript", "java", "c#", "c++", "c",
    "go", "golang", "rust", "ruby", "php", "swift", "kotlin", "scala",
    "r", "perl", "lua", "dart", "elixir", "haskell", "matlab",
    "sql", "html", "css", "sass", "less", "graphql", "bash", "shell",
    "pick basic",
    # Frontend
    "react", "angular", "vue", "svelte", "next.js", "nextjs", "nuxt",
    "gatsby", "remix", "ember", "backbone", "jquery",
    "tailwind", "bootstrap", "chakra ui", "material ui", "styled-components",
    # Backend
    "node.js", "nodejs", "express", "flask", "django", "fastapi",
    "spring", "spring boot", ".net", "asp.net", "rails", "laravel",
    "gin", "fiber", "actix", "rocket",
    # Databases
    "postgresql", "postgres", "mysql", "mongodb", "redis", "elasticsearch",
    "dynamodb", "cassandra", "sqlite", "oracle", "sql server", "mariadb",
    "neo4j", "couchdb", "firestore", "supabase",
    # Cloud & DevOps
    "aws", "gcp", "azure", "docker", "kubernetes", "k8s",
    "terraform", "ansible", "puppet", "chef", "vagrant",
    "jenkins", "github actions", "gitlab ci", "circleci", "travis ci",
    "ci/cd", "nginx", "apache", "vercel", "heroku", "netlify",
    "cloudflare", "digitalocean", "linode",
    # Data & ML
    "pandas", "numpy", "scipy", "scikit-learn", "tensorflow",
    "pytorch", "keras", "spark", "hadoop", "airflow", "dbt",
    "kafka", "rabbitmq", "celery", "luigi",
    "tableau", "power bi", "looker", "grafana",
    # Mobile
    "react native", "flutter", "swift ui", "swiftui", "jetpack compose",
    "ionic", "xamarin", "expo",
    # Tools & Misc
    "git", "jira", "confluence", "figma", "postman",
    "linux", "unix", "windows", "macos",
    "rest api", "grpc", "websockets", "oauth", "jwt",
    "agile", "scrum", "kanban",
    # Quantum (specific to your background)
    "qiskit", "sequence", "cirq", "pennylane",
}

# Common title keywords to look for in experience sections
TITLE_PATTERNS = [
    "software developer", "software engineer", "senior software engineer",
    "staff software engineer", "principal engineer", "lead engineer",
    "frontend developer", "frontend engineer", "backend developer",
    "backend engineer", "full stack developer", "full stack engineer",
    "fullstack developer", "fullstack engineer",
    "devops engineer", "cloud engineer", "platform engineer",
    "site reliability engineer", "sre",
    "data engineer", "data scientist", "data analyst",
    "machine learning engineer", "ml engineer", "ai engineer",
    "mobile developer", "ios developer", "android developer",
    "qa engineer", "test engineer", "security engineer",
    "research assistant", "research engineer", "research scientist",
    "technical lead", "engineering manager", "tech lead",
    "solutions architect", "systems engineer", "network engineer",
]

# Domain keywords to extract from job descriptions
KNOWN_KEYWORDS = {
    "data pipeline", "full-stack", "full stack", "rest api", "api",
    "cloud", "machine learning", "deep learning", "artificial intelligence",
    "computer vision", "natural language processing", "nlp",
    "devops", "microservices", "serverless", "event-driven",
    "front end", "frontend", "back end", "backend",
    "web application", "mobile application",
    "distributed systems", "real-time", "streaming",
    "etl", "data warehouse", "data lake",
    "authentication", "authorization", "security",
    "monitoring", "observability", "logging",
    "containerization", "orchestration", "infrastructure as code",
    "pose estimation", "facial recognition", "quantum",
}


def extract_text(pdf_path):
    """Extract all text from a PDF file."""
    doc = fitz.open(pdf_path)
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    return text


def find_skills(text):
    """Find known tech skills mentioned in the resume text."""
    text_lower = text.lower()
    found = set()
    for skill in KNOWN_SKILLS:
        # Use word boundaries for all skills to avoid substring false positives
        # e.g. "java" in "javascript", "ember" in "member", "gin" in "engineering"
        if re.search(rf"(?<![a-z]){re.escape(skill)}(?![a-z])", text_lower):
            found.add(skill)
    return found


def find_titles(text):
    """Find job titles from the experience section."""
    text_lower = text.lower()
    found = []
    for title in TITLE_PATTERNS:
        if title in text_lower:
            found.append(title)
    return found


def find_keywords(text):
    """Find domain keywords mentioned in the resume."""
    text_lower = text.lower()
    found = set()
    for kw in KNOWN_KEYWORDS:
        if kw in text_lower:
            found.add(kw)
    return found


def format_set(items, name):
    """Format a set as a Python set literal for config.py."""
    sorted_items = sorted(items)
    lines = [f"{name} = {{"]
    for i, item in enumerate(sorted_items):
        comma = "," if i < len(sorted_items) - 1 else ","
        lines.append(f'    "{item}"{comma}')
    lines.append("}")
    return "\n".join(lines)


def format_list(items, name):
    """Format a list as a Python list literal for config.py."""
    lines = [f"{name} = ["]
    for i, item in enumerate(items):
        comma = "," if i < len(items) - 1 else ","
        lines.append(f'    "{item}"{comma}')
    lines.append("]")
    return "\n".join(lines)


def update_config(skills, cloud_skills, titles, keywords):
    """Update config.py with new resume data."""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.py")

    with open(config_path) as f:
        content = f.read()

    # Separate cloud skills from general skills
    cloud = {"aws", "gcp", "azure"}
    found_cloud = skills & cloud
    general_skills = skills - cloud

    # Build replacement blocks
    skills_block = format_set(general_skills, "RESUME_SKILLS")
    cloud_block = format_set(found_cloud if found_cloud else cloud_skills, "RESUME_CLOUD")
    titles_block = format_list(titles, "RESUME_TITLES")
    keywords_block = format_set(keywords, "RESUME_KEYWORDS")

    # Replace each section using regex
    def replace_block(content, var_name, new_block):
        # Match from variable assignment through closing brace/bracket
        pattern = rf"{var_name}\s*=\s*[\{{\[].*?[\}}\]]"
        match = re.search(pattern, content, re.DOTALL)
        if match:
            return content[:match.start()] + new_block + content[match.end():]
        return content

    content = replace_block(content, "RESUME_SKILLS", skills_block)
    content = replace_block(content, "RESUME_CLOUD", cloud_block)
    content = replace_block(content, "RESUME_TITLES", titles_block)
    content = replace_block(content, "RESUME_KEYWORDS", keywords_block)

    with open(config_path, "w") as f:
        f.write(content)

    return config_path


def find_pdf():
    """Find the first PDF in the project directory."""
    project_dir = os.path.dirname(os.path.abspath(__file__))
    for f in os.listdir(project_dir):
        if f.lower().endswith(".pdf"):
            return os.path.join(project_dir, f)
    return None


def main():
    # Get PDF path from argument or find one
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
    else:
        pdf_path = find_pdf()

    if not pdf_path or not os.path.exists(pdf_path):
        print("Usage: pipenv run python update_resume.py [path/to/resume.pdf]")
        print("No PDF found in the project directory.")
        return

    print(f"Reading: {os.path.basename(pdf_path)}")
    text = extract_text(pdf_path)
    print(f"Extracted {len(text)} characters\n")

    # Extract data
    skills = find_skills(text)
    titles = find_titles(text)
    keywords = find_keywords(text)

    # Separate cloud skills for display
    cloud = {"aws", "gcp", "azure"}
    cloud_skills = skills & cloud
    general_skills = skills - cloud

    print(f"Skills found ({len(general_skills)}):")
    for s in sorted(general_skills):
        print(f"  - {s}")

    print(f"\nCloud platforms ({len(cloud_skills)}):")
    for s in sorted(cloud_skills):
        print(f"  - {s}")

    print(f"\nTitles found ({len(titles)}):")
    for t in titles:
        print(f"  - {t}")

    print(f"\nKeywords found ({len(keywords)}):")
    for k in sorted(keywords):
        print(f"  - {k}")

    # Confirm before updating
    print()
    answer = input("Update config.py with these values? [Y/n] ").strip().lower()
    if answer and answer != "y":
        print("Aborted.")
        return

    config_path = update_config(skills, cloud_skills, titles, keywords)
    print(f"\nUpdated {config_path}")
    print("Run 'pipenv run python main.py' to search with the new resume data.")


if __name__ == "__main__":
    main()
