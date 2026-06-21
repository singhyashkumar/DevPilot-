"""Frontend payload builders for the FastAPI dashboard.

This module intentionally keeps the web UI independent from the analyzer's
internal dataclasses.  The analyzer can evolve without forcing template or
JavaScript changes across the dashboard.
"""

from __future__ import annotations

import re
from typing import Any

from devpilot.models import CodeIssue, RepositoryReport


GRADE_DESCRIPTIONS = {
    "Excellent": "A polished repository with strong engineering signals across the audit.",
    "Good": "A solid repository with a few focused improvements left to make.",
    "Average": "A workable repository that will benefit from structured cleanup.",
    "Needs Improvement": "Important engineering foundations should be improved before publishing.",
    "Poor": "The repository needs core structure, quality, or safety work before it is showcase-ready.",
}


def report_to_dashboard_payload(report: RepositoryReport) -> dict[str, Any]:
    """Translate a repository report into the stable schema consumed by the UI."""
    code_score: int | None = report.code_quality.score if report.code_quality.is_applicable else None
    return {
        "repoName": report.repository_name,
        "repoUrl": report.source,
        "overallScore": report.score.overall_score,
        "grade": report.score.grade,
        "gradeDescription": GRADE_DESCRIPTIONS.get(report.score.grade, "Repository audit completed."),
        "breakdown": {
            "codeQuality": code_score,
            "documentation": report.readme.score,
            "testing": report.testing.score,
            "security": report.security.score,
            "dependencies": report.dependencies.score,
            "structure": report.structure.score,
        },
        "stats": {
            "totalFiles": report.total_files,
            "sourceFiles": report.source_files,
            "pythonFiles": report.python_files,
            "testFiles": report.testing.test_files_count,
            "dependencies": report.dependencies.total_dependencies,
            "languages": len(report.languages),
        },
        "strongPoints": report.score.strong_points,
        "weakPoints": report.score.weak_points,
        "topIssues": report.score.top_issues,
        "roadmap": _roadmap_cards(report.score.roadmap),
        "codeIssues": [_code_issue_payload(issue) for issue in report.code_quality.issues[:60]],
        "securityIssues": [_security_issue_payload(warning) for warning in report.security.warnings[:40]],
        "recommendations": _recommendations(report),
        "languages": [_language_payload(item) for item in report.code_quality.language_breakdown],
        "analysis": {
            "estimatedSeconds": report.analysis_timing.estimated_seconds,
            "actualSeconds": round(report.analysis_timing.actual_seconds, 2),
            "confidence": report.analysis_timing.confidence,
            "languageLabel": report.language,
            "languageCounts": report.languages,
            "codeQualityApplicable": report.code_quality.is_applicable,
            "codeQualityReason": report.code_quality.not_applicable_reason,
        },
    }


def _code_issue_payload(issue: CodeIssue) -> dict[str, str]:
    """Return a browser-ready code issue with conservative labels."""
    return {
        "type": issue.language or "code quality",
        "severity": _normalize_severity(issue.severity),
        "description": issue.message,
        "location": issue.file,
    }


def _security_issue_payload(warning: str) -> dict[str, str]:
    """Make scanner security warnings consistent with the code-issue panel."""
    text = warning.strip()
    location = _extract_location(text)
    return {
        "type": "security warning",
        "severity": _security_severity(text),
        "description": text,
        "location": location or "Repository scan",
    }


def _language_payload(item: Any) -> dict[str, Any]:
    """Create one visual language-health card payload."""
    return {
        "name": item.language,
        "score": item.score,
        "files": item.file_count,
        "lines": item.total_lines,
        "functions": item.total_functions,
        "comments": item.comment_lines,
        "commentRatio": round(item.comment_ratio * 100, 1),
        "issues": [_code_issue_payload(issue) for issue in item.issues[:8]],
    }


def _roadmap_cards(items: list[str]) -> list[dict[str, Any]]:
    """Turn the score engine's readable roadmap strings into styled timeline cards."""
    cards: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        match = re.match(r"^(Phase\s+\d+|Final Phase):\s*(.*)$", item.strip(), flags=re.IGNORECASE)
        phase = match.group(1) if match else f"Phase {index}"
        instruction = match.group(2) if match else item.strip()
        title, tasks = _split_roadmap_instruction(instruction)
        cards.append(
            {
                "phase": phase.replace("Phase ", "").replace("Final Phase", "Final"),
                "title": title,
                "priority": _roadmap_priority(instruction, index),
                "tasks": tasks,
            }
        )
    return cards


def _split_roadmap_instruction(instruction: str) -> tuple[str, list[str]]:
    """Give the timeline a short heading and a useful task sentence."""
    clean = instruction.strip().rstrip(".")
    clauses = [segment.strip() for segment in re.split(r";\s*", clean) if segment.strip()]
    if not clauses:
        return "Repository improvement", ["Review the audit findings and apply the recommended changes."]
    first = clauses[0]
    title = first
    if len(first) > 74:
        boundary = first.find(",")
        title = first[:boundary].strip() if boundary > 18 else first[:74].rsplit(" ", 1)[0]
    tasks = clauses if len(clauses) > 1 else [first]
    return title, tasks


def _recommendations(report: RepositoryReport) -> list[str]:
    """Collect non-duplicated recommended actions from the analyzer modules."""
    candidates = [
        *report.readme.suggestions,
        *report.testing.suggestions,
        *report.structure.suggestions,
        *report.dependencies.warnings,
        *report.score.roadmap,
    ]
    unique: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        clean = item.strip()
        key = clean.casefold()
        if clean and key not in seen:
            seen.add(key)
            unique.append(clean)
        if len(unique) == 30:
            break
    return unique or ["No additional recommendation was generated for this repository."]


def _extract_location(text: str) -> str:
    """Best-effort location hint for warning text without inventing a file path."""
    match = re.search(r"(?:in|at)\s+([\w./\\-]+(?::\d+)?)", text, flags=re.IGNORECASE)
    return match.group(1) if match else ""


def _security_severity(text: str) -> str:
    lowered = text.casefold()
    if any(token in lowered for token in ("secret", "api key", "password", "token", "private key", "eval(")):
        return "high"
    if any(token in lowered for token in ("subprocess", "pickle", "yaml", ".env", "unsafe")):
        return "medium"
    return "low"


def _roadmap_priority(text: str, index: int) -> str:
    lowered = text.casefold()
    if any(token in lowered for token in ("security", "secret", "hardcoded", "eval", ".env")):
        return "critical"
    if index <= 2 or any(token in lowered for token in ("test", "readme", "documentation")):
        return "high"
    if index <= 4:
        return "medium"
    return "low"


def _normalize_severity(value: str) -> str:
    """Protect the CSS contract when an analyzer adds a new severity value."""
    return value.lower() if value.lower() in {"low", "medium", "high", "critical"} else "medium"
