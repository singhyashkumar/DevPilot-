"""JSON, Markdown, and HTML report exporters."""

from __future__ import annotations

import html
import json
from pathlib import Path

from devpilot.models import RepositoryReport
from devpilot.utils import ensure_directory


class ReportGenerator:
    """Export DevPilot repository reports."""

    def __init__(self, output_dir: str | Path = "reports") -> None:
        self.output_dir = ensure_directory(Path(output_dir))

    def export_all(self, report: RepositoryReport, base_name: str = "devpilot_report") -> dict[str, Path]:
        """Export JSON, Markdown, and HTML representations of one report."""
        return {
            "json": self.export_json(report, f"{base_name}.json"),
            "markdown": self.export_markdown(report, f"{base_name}.md"),
            "html": self.export_html(report, f"{base_name}.html"),
        }

    def export_json(self, report: RepositoryReport, filename: str = "devpilot_report.json") -> Path:
        """Write a machine-readable JSON report and return its path."""
        path = self.output_dir / filename
        path.write_text(json.dumps(report.as_dict(), indent=2, default=str), encoding="utf-8")
        return path

    def export_markdown(self, report: RepositoryReport, filename: str = "devpilot_report.md") -> Path:
        """Write a GitHub-ready Markdown report and return its path."""
        path = self.output_dir / filename
        path.write_text(self.to_markdown(report), encoding="utf-8")
        return path

    def export_html(self, report: RepositoryReport, filename: str = "devpilot_report.html") -> Path:
        """Write a standalone browser report and return its path."""
        path = self.output_dir / filename
        path.write_text(self.to_html(report), encoding="utf-8")
        return path

    @classmethod
    def to_markdown(cls, report: RepositoryReport) -> str:
        """Build a Markdown report without writing temporary files."""
        score = report.score
        lines = [
            f"# DevPilot Repository Report — {report.repository_name}",
            "",
            "## Summary",
            "",
            f"- **Repository:** {report.repository_name}",
            f"- **Language:** {report.language}",
            f"- **Total Files:** {report.total_files}",
            f"- **Source Files:** {report.source_files}",
            f"- **Python Files:** {report.python_files}",
            f"- **Languages Detected:** {', '.join(f'{name} ({count})' for name, count in report.languages.items()) or 'No supported source detected'}",
            f"- **Analysis Time:** {report.analysis_timing.actual_seconds:.2f} sec",
            f"- **Overall Score:** {score.overall_score}/100",
            f"- **Grade:** {score.grade}",
            "",
            "## Score Breakdown",
            "",
            "| Area | Score |",
            "|---|---:|",
            f"| Code Quality | {cls._score_text(report.code_quality.score, report.code_quality.is_applicable)} |",
            f"| Documentation | {report.readme.score}/100 |",
            f"| Testing | {report.testing.score}/100 |",
            f"| Security | {report.security.score}/100 |",
            f"| Dependencies | {report.dependencies.score}/100 |",
            f"| Structure | {report.structure.score}/100 |",
            "",
            "## Language Quality Breakdown",
            "",
        ]
        if report.code_quality.language_breakdown:
            lines.extend(["| Language | Files | Lines | Functions | Score |", "|---|---:|---:|---:|---:|"])
            lines.extend(
                [
                    f"| {item.language} | {item.file_count} | {item.total_lines} | {item.total_functions} | {item.score}/100 |"
                    for item in report.code_quality.language_breakdown
                ]
            )
        else:
            lines.append("- No supported production source files were analyzed.")
        lines.extend(["", "## Strong Points", ""])
        lines.extend([f"- {item}" for item in score.strong_points])
        lines.extend(["", "## Weak Points", ""])
        lines.extend([f"- {item}" for item in score.weak_points] or ["- No major weak point detected"])
        lines.extend(["", "## Top Issues", ""])
        lines.extend([f"{index}. {item}" for index, item in enumerate(score.top_issues, start=1)])
        lines.extend(["", "## Recommended Roadmap", ""])
        lines.extend([f"{index}. {item}" for index, item in enumerate(score.roadmap, start=1)])
        lines.extend(["", "## File-Level Code Issues", ""])
        if report.code_quality.issues:
            lines.extend([f"- **{issue.severity.upper()}** `{issue.file}` — {issue.message}" for issue in report.code_quality.issues[:50]])
        else:
            lines.append("- No file-level code issue detected.")
        lines.extend(["", "## Security Warnings", ""])
        lines.extend([f"- {item}" for item in report.security.warnings] or ["- No security warning detected."])
        lines.extend(["", "## README Missing Sections", ""])
        lines.extend([f"- {item}" for item in report.readme.missing_sections] or ["- README contains all required sections."])
        return "\n".join(lines) + "\n"

    @classmethod
    def to_html(cls, report: RepositoryReport) -> str:
        """Build a standalone HTML report without writing temporary files."""
        data = report.as_dict()
        code_score: int | None = report.code_quality.score if report.code_quality.is_applicable else None
        card_html = "\n".join(
            cls._score_card(title, value)
            for title, value in [
                ("Overall", report.score.overall_score),
                ("Code Quality", code_score),
                ("Documentation", report.readme.score),
                ("Testing", report.testing.score),
                ("Security", report.security.score),
                ("Dependencies", report.dependencies.score),
                ("Structure", report.structure.score),
            ]
        )
        top_issues = "".join(f"<li>{html.escape(item)}</li>" for item in report.score.top_issues)
        roadmap = "".join(f"<li>{html.escape(item)}</li>" for item in report.score.roadmap)
        language_rows = "".join(
            f"<tr><td>{html.escape(item.language)}</td><td>{item.file_count}</td><td>{item.total_lines}</td><td>{item.total_functions}</td><td>{item.score}/100</td></tr>"
            for item in report.code_quality.language_breakdown
        ) or "<tr><td colspan='5'>No supported production source files were analyzed.</td></tr>"
        raw_json = html.escape(json.dumps(data, indent=2, default=str))
        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>DevPilot Report - {html.escape(report.repository_name)}</title>
  <style>
    body {{ margin: 0; font-family: Inter, Segoe UI, Arial, sans-serif; background: #0f172a; color: #e5e7eb; }}
    .container {{ max-width: 1100px; margin: 0 auto; padding: 32px; }}
    .hero {{ background: linear-gradient(135deg, #111827, #1e293b); border: 1px solid #334155; border-radius: 18px; padding: 28px; }}
    h1 {{ margin: 0 0 8px; }}
    .muted {{ color: #94a3b8; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; margin: 24px 0; }}
    .card {{ background: #111827; border: 1px solid #334155; border-radius: 16px; padding: 18px; }}
    .score {{ font-size: 32px; font-weight: 800; color: #38bdf8; }}
    .bar {{ width: 100%; height: 10px; background: #334155; border-radius: 999px; overflow: hidden; margin-top: 10px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }} th,td {{ text-align: left; padding: 10px; border-bottom: 1px solid #334155; }} th {{ color: #94a3b8; }}
    .fill {{ height: 100%; background: linear-gradient(90deg, #22c55e, #38bdf8); }}
    li {{ margin-bottom: 8px; }}
    pre {{ background: #020617; border: 1px solid #334155; padding: 18px; border-radius: 12px; overflow-x: auto; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="hero">
      <h1>DevPilot Repository Report</h1>
      <p class="muted">Repository: {html.escape(report.repository_name)} · Grade: {html.escape(report.score.grade)} · Languages: {html.escape(report.language)}</p>
    </div>
    <div class="grid">{card_html}</div>
    <div class="card"><h2>Language Quality Breakdown</h2><table><thead><tr><th>Language</th><th>Files</th><th>Lines</th><th>Functions</th><th>Score</th></tr></thead><tbody>{language_rows}</tbody></table></div>
    <div class="card"><h2>Top Issues</h2><ol>{top_issues}</ol></div>
    <div class="card"><h2>Recommended Roadmap</h2><ol>{roadmap}</ol></div>
    <div class="card"><h2>Raw JSON</h2><pre>{raw_json}</pre></div>
  </div>
</body>
</html>"""

    @staticmethod
    def _score_text(value: int, is_applicable: bool) -> str:
        """Render a score safely when no supported production-code audit is applicable."""
        return f"{value}/100" if is_applicable else "N/A"

    @staticmethod
    def _score_card(title: str, value: int | None) -> str:
        """Create one report score card, supporting scope-aware N/A values."""
        safe_title = html.escape(title)
        if value is None:
            return f"""
            <div class="card">
              <div class="muted">{safe_title}</div>
              <div class="score">N/A</div>
              <div class="bar"><div class="fill" style="width:12%;opacity:.35"></div></div>
            </div>
            """
        safe_value = max(0, min(100, int(value)))
        return f"""
        <div class="card">
          <div class="muted">{safe_title}</div>
          <div class="score">{safe_value}/100</div>
          <div class="bar"><div class="fill" style="width:{safe_value}%"></div></div>
        </div>
        """
