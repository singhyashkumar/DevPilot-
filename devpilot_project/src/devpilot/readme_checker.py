"""README quality checker for DevPilot."""

from __future__ import annotations

import re

from devpilot.models import ReadmeResult, ScanResult
from devpilot.utils import relative_posix, safe_read_text


class ReadmeChecker:
    """Check whether README contains the sections recruiters and users expect."""

    REQUIRED_SECTIONS = {
        "project title": [r"^#\s+.+"],
        "short description": [r"(?i)description", r"(?i)overview", r"(?i)about", r"(?i)what is"],
        "features": [r"(?i)^#+\s*features?", r"(?i)key features"],
        "installation": [r"(?i)^#+\s*installation", r"(?i)install", r"pip install"],
        "usage": [r"(?i)^#+\s*usage", r"(?i)how to use", r"python .*\.py"],
        "screenshots": [r"(?i)^#+\s*screenshots?", r"!\[.*\]\(.*\)"],
        "tech stack": [r"(?i)tech stack", r"(?i)technologies", r"(?i)built with"],
        "folder structure": [r"(?i)folder structure", r"(?i)project structure", r"```text"],
        "roadmap": [r"(?i)^#+\s*roadmap", r"(?i)future scope", r"(?i)planned"],
        "license": [r"(?i)^#+\s*license", r"(?i)MIT License", r"(?i)Apache"],
        "contact": [r"(?i)^#+\s*contact", r"(?i)author", r"(?i)email", r"(?i)github.com"],
    }

    def __init__(self, scan: ScanResult) -> None:
        self.scan = scan

    def analyze(self) -> ReadmeResult:
        if not self.scan.readme_file:
            return ReadmeResult(
                score=0,
                found=False,
                path=None,
                word_count=0,
                missing_sections=list(self.REQUIRED_SECTIONS),
                suggestions=["Create README.md with title, description, features, installation, usage, screenshots, roadmap, license, and contact."],
            )

        text = safe_read_text(self.scan.readme_file)
        word_count = len(re.findall(r"\b\w+\b", text))
        present: list[str] = []
        missing: list[str] = []

        for section, patterns in self.REQUIRED_SECTIONS.items():
            if any(re.search(pattern, text, flags=re.MULTILINE) for pattern in patterns):
                present.append(section)
            else:
                missing.append(section)

        score = 100
        score -= len(missing) * 7
        if word_count < 80:
            score -= 20
        elif word_count < 200:
            score -= 8
        if "```" not in text and "usage" in missing:
            score -= 5

        suggestions = [f"Add README section: {section.title()}" for section in missing]
        if word_count < 200:
            suggestions.append("Expand README with clear explanation, commands, and examples.")
        if "screenshots" in missing:
            suggestions.append("Add screenshots or a GIF demo to make the project look portfolio-ready.")

        return ReadmeResult(
            score=max(score, 0),
            found=True,
            path=relative_posix(self.scan.readme_file, self.scan.root_path),
            word_count=word_count,
            present_sections=present,
            missing_sections=missing,
            suggestions=suggestions,
        )
