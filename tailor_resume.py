"""
Tailor a one-page resume to a specific job using Claude API.

Reads your full experience from experience.json, calls Claude to select and
rewrite the most relevant content, then renders a clean PDF.

Usage (standalone):
    pipenv run python tailor_resume.py

Or called automatically from main.py after scoring jobs.

Requirements:
    ANTHROPIC_API_KEY in .env (or environment)
"""

import json
import os
import sys
from datetime import date
from pathlib import Path

from config import load_env

EXPERIENCE_PATH = Path(__file__).parent / "experience.json"
OUTPUT_DIR = Path(__file__).parent / "tailored_resumes"


# ---------------------------------------------------------------------------
# Experience loader
# ---------------------------------------------------------------------------

def load_experience():
    """Load master experience JSON. Returns None and prints help if missing."""
    if not EXPERIENCE_PATH.exists():
        print(f"\nError: {EXPERIENCE_PATH} not found.")
        print("Create experience.json with your full work history.")
        print("Copy experience.json.example as a starting point.\n")
        return None
    with open(EXPERIENCE_PATH) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Claude tailoring
# ---------------------------------------------------------------------------

def tailor_with_claude(experience: dict, job_title: str, job_company: str, job_description: str) -> dict:
    """
    Call Claude to select the most relevant experience and tailor bullet points
    for the given job. Returns a dict with keys:
        summary, selected_experience, selected_projects, skills_highlight
    """
    import anthropic

    client = anthropic.Anthropic()

    system = """You are an expert resume writer. Given a candidate's full experience and a job description:

1. Select 2-3 of the most relevant work experience entries.
2. Select 2-3 of the most relevant projects.
3. Rewrite bullets to emphasize skills and keywords from the job description (stay truthful).
4. Keep each bullet under 110 characters.
5. Prioritize quantifiable achievements.
6. Write a one-sentence professional summary tailored to this role, or null if nothing specific to say.
7. List the most relevant skills to highlight at the bottom.

Return ONLY valid JSON — no markdown, no explanation — matching this exact structure:
{
  "summary": "one sentence or null",
  "selected_experience": [
    {
      "title": "...", "company": "...", "location": "...",
      "start_date": "...", "end_date": "...",
      "bullets": ["...", "...", "..."]
    }
  ],
  "selected_projects": [
    {
      "name": "...", "technologies": ["...", "..."],
      "bullets": ["...", "..."]
    }
  ],
  "skills_highlight": ["skill1", "skill2", "..."]
}"""

    user_msg = (
        f"Target Role: {job_title} at {job_company}\n\n"
        f"Job Description:\n{job_description[:3500]}\n\n"
        f"Full Experience:\n{json.dumps(experience, indent=2)}"
    )

    print("    Calling Claude to tailor content...", end="", flush=True)

    with client.messages.stream(
        model="claude-opus-4-6",
        max_tokens=3000,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    ) as stream:
        final = stream.get_final_message()

    print(" done.")

    text = next(b.text for b in final.content if b.type == "text").strip()

    # Strip markdown code fences if Claude wraps the JSON anyway
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0].strip()

    return json.loads(text)


# ---------------------------------------------------------------------------
# PDF generation
# ---------------------------------------------------------------------------

def generate_pdf(experience: dict, tailored: dict, job_title: str, job_company: str) -> Path:
    """Render a one-page PDF resume from the tailored content dict."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        HRFlowable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    OUTPUT_DIR.mkdir(exist_ok=True)

    safe = "".join(c if c.isalnum() or c == " " else "" for c in job_company).strip().replace(" ", "_")
    filename = f"resume_{safe}_{date.today()}.pdf"
    output_path = OUTPUT_DIR / filename

    contact = experience.get("contact", {})
    education = experience.get("education", [])
    skills = experience.get("skills", {})

    # --- Style definitions ---
    DARK = colors.HexColor("#1a1a1a")
    MID = colors.HexColor("#555555")
    RULE = colors.HexColor("#cccccc")

    name_style = ParagraphStyle(
        "Name", fontName="Helvetica-Bold", fontSize=18,
        alignment=TA_CENTER, spaceAfter=3, textColor=DARK,
    )
    contact_style = ParagraphStyle(
        "Contact", fontName="Helvetica", fontSize=9,
        alignment=TA_CENTER, spaceAfter=5, textColor=MID,
    )
    section_style = ParagraphStyle(
        "Section", fontName="Helvetica-Bold", fontSize=10,
        spaceBefore=9, spaceAfter=2, textColor=DARK,
    )
    entry_title_style = ParagraphStyle(
        "EntryTitle", fontName="Helvetica-Bold", fontSize=10, spaceAfter=0,
    )
    date_style = ParagraphStyle(
        "Date", fontName="Helvetica", fontSize=9,
        alignment=TA_RIGHT, textColor=MID,
    )
    meta_style = ParagraphStyle(
        "Meta", fontName="Helvetica-Oblique", fontSize=9,
        spaceAfter=2, textColor=MID,
    )
    bullet_style = ParagraphStyle(
        "Bullet", fontName="Helvetica", fontSize=9,
        leftIndent=12, firstLineIndent=-8, spaceAfter=1,
    )
    body_style = ParagraphStyle(
        "Body", fontName="Helvetica", fontSize=9, spaceAfter=4,
    )

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        leftMargin=0.55 * inch,
        rightMargin=0.55 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.45 * inch,
    )

    story = []

    # Header
    story.append(Paragraph(contact.get("name", ""), name_style))
    contact_parts = [p for p in [
        contact.get("email"), contact.get("phone"), contact.get("location"),
        contact.get("linkedin"), contact.get("github"),
    ] if p]
    story.append(Paragraph(" | ".join(contact_parts), contact_style))
    story.append(HRFlowable(width="100%", thickness=1.2, color=DARK, spaceAfter=2))

    # Summary
    summary = tailored.get("summary")
    if summary:
        story.append(Paragraph("PROFESSIONAL SUMMARY", section_style))
        story.append(HRFlowable(width="100%", thickness=0.5, color=RULE, spaceAfter=3))
        story.append(Paragraph(summary, body_style))

    # Experience
    experience_entries = tailored.get("selected_experience", [])
    if experience_entries:
        story.append(Paragraph("EXPERIENCE", section_style))
        story.append(HRFlowable(width="100%", thickness=0.5, color=RULE, spaceAfter=3))

        for exp in experience_entries:
            date_range = f"{exp.get('start_date', '')} \u2013 {exp.get('end_date', '')}"
            header = Table(
                [[Paragraph(exp.get("title", ""), entry_title_style),
                  Paragraph(date_range, date_style)]],
                colWidths=["68%", "32%"],
            )
            header.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
            ]))
            story.append(header)
            story.append(Paragraph(
                f"{exp.get('company', '')} \u2014 {exp.get('location', '')}",
                meta_style,
            ))
            for bullet in exp.get("bullets", []):
                story.append(Paragraph(f"\u2022  {bullet}", bullet_style))
            story.append(Spacer(1, 3))

    # Projects
    projects = tailored.get("selected_projects", [])
    if projects:
        story.append(Paragraph("PROJECTS", section_style))
        story.append(HRFlowable(width="100%", thickness=0.5, color=RULE, spaceAfter=3))

        for proj in projects:
            techs = ", ".join(proj.get("technologies", []))
            header_text = f"<b>{proj.get('name', '')}</b>"
            if techs:
                header_text += f'  <font name="Helvetica-Oblique" color="#555555" size="9">({techs})</font>'
            story.append(Paragraph(header_text, entry_title_style))
            for bullet in proj.get("bullets", []):
                story.append(Paragraph(f"\u2022  {bullet}", bullet_style))
            story.append(Spacer(1, 3))

    # Education
    if education:
        story.append(Paragraph("EDUCATION", section_style))
        story.append(HRFlowable(width="100%", thickness=0.5, color=RULE, spaceAfter=3))
        for edu in education:
            gpa = f" | GPA: {edu['gpa']}" if edu.get("gpa") else ""
            story.append(Paragraph(
                f"<b>{edu.get('degree', '')}</b> \u2014 "
                f"{edu.get('institution', '')} | {edu.get('graduation', '')}{gpa}",
                body_style,
            ))
            if edu.get("relevant_courses"):
                story.append(Paragraph(
                    f"Relevant Courses: {', '.join(edu['relevant_courses'])}",
                    body_style,
                ))

    # Skills
    story.append(Paragraph("SKILLS", section_style))
    story.append(HRFlowable(width="100%", thickness=0.5, color=RULE, spaceAfter=3))

    highlighted = tailored.get("skills_highlight") or []
    if not highlighted:
        for cat_skills in skills.values():
            highlighted.extend(cat_skills)
    story.append(Paragraph(" \u2022 ".join(highlighted), body_style))

    doc.build(story)
    return output_path


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

def main():
    load_env()

    experience = load_experience()
    if not experience:
        return

    print("=== Resume Tailor ===")
    job_title = input("Job Title: ").strip() or "Software Engineer"
    job_company = input("Company: ").strip() or "Company"
    print("Paste the job description, then press Ctrl+D (or Ctrl+Z on Windows):")
    try:
        job_description = sys.stdin.read()
    except KeyboardInterrupt:
        print("\nAborted.")
        return

    if not job_description.strip():
        print("No description provided. Exiting.")
        return

    print(f"\nTailoring resume for {job_title} at {job_company}...")
    tailored = tailor_with_claude(experience, job_title, job_company, job_description)
    pdf_path = generate_pdf(experience, tailored, job_title, job_company)
    print(f"\nResume saved to: {pdf_path}")


if __name__ == "__main__":
    main()
