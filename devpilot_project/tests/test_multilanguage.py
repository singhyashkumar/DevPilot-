"""Regression tests for DevPilot's language-aware repository audits."""

from __future__ import annotations

from pathlib import Path

from devpilot.analyzer import CodeQualityAnalyzer, TestingAnalyzer
from devpilot.dependency_checker import DependencyChecker
from devpilot.main import analyze_repository
from devpilot.report_generator import ReportGenerator
from devpilot.scanner import RepositoryScanner


def test_scanner_detects_a_mixed_language_repository(tmp_path: Path) -> None:
    """Supported source languages must be visible before quality scoring starts."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "api.ts").write_text("export const ping = (): string => 'pong';\n", encoding="utf-8")
    (tmp_path / "src" / "Worker.java").write_text("class Worker { void run() {} }\n", encoding="utf-8")
    (tmp_path / "src" / "service.go").write_text("package service\nfunc Run() {}\n", encoding="utf-8")
    (tmp_path / "package.json").write_text('{"name":"demo","dependencies":{"express":"^5.0.0"}}', encoding="utf-8")

    scan = RepositoryScanner(tmp_path).scan()

    assert scan.source_file_count == 3
    assert scan.language_counts == {"Go": 1, "Java": 1, "TypeScript": 1}
    assert scan.has_dependency_file is True


def test_javascript_repository_gets_a_real_quality_score(tmp_path: Path) -> None:
    """JavaScript must no longer be marked N/A because it is not Python."""
    (tmp_path / "app.js").write_text(
        "function greet(name) {\n  console.log(name);\n  return `Hello ${name}`;\n}\n",
        encoding="utf-8",
    )

    report = analyze_repository(tmp_path)

    assert report.language == "JavaScript"
    assert report.code_quality.is_applicable is True
    assert report.code_quality.score > 0
    assert report.code_quality.analyzed_languages == ["JavaScript"]
    assert report.code_quality.language_breakdown[0].score < 100
    assert any("debug output" in issue.message for issue in report.code_quality.issues)


def test_mixed_language_score_exposes_each_language(tmp_path: Path) -> None:
    """A mixed repository must preserve separate language scores in the final report."""
    (tmp_path / "core.py").write_text(
        '"""Core module."""\n\ndef add(left: int, right: int) -> int:\n    """Add values."""\n    return left + right\n',
        encoding="utf-8",
    )
    (tmp_path / "web.ts").write_text("export const add = (left: number, right: number) => left + right;\n", encoding="utf-8")

    report = analyze_repository(tmp_path)

    assert report.code_quality.is_applicable is True
    assert set(report.code_quality.analyzed_languages) == {"Python", "TypeScript"}
    assert report.language == "Python (1) + TypeScript (1)"
    assert {item.language for item in report.code_quality.language_breakdown} == {"Python", "TypeScript"}


def test_testing_analyzer_detects_jest_style_tests(tmp_path: Path) -> None:
    """The test readiness score must recognize JavaScript test conventions."""
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "math.ts").write_text("export const add = (a: number, b: number) => a + b;\n", encoding="utf-8")
    (tmp_path / "tests" / "math.test.ts").write_text("import { test, expect } from 'vitest';\ntest('add', () => expect(1 + 1).toBe(2));\n", encoding="utf-8")

    result = TestingAnalyzer(RepositoryScanner(tmp_path).scan()).analyze()

    assert "Jest / Vitest" in result.frameworks_detected
    assert result.score >= 70


def test_node_dependency_manifest_is_not_penalized_for_missing_pyproject(tmp_path: Path) -> None:
    """Node repositories must be graded from package.json, not Python packaging rules."""
    (tmp_path / "package.json").write_text(
        '{"name":"demo","dependencies":{"express":"^5.0.0"},"devDependencies":{"vitest":"^3.0.0"}}',
        encoding="utf-8",
    )
    scan = RepositoryScanner(tmp_path).scan()

    result = DependencyChecker(scan).analyze()

    assert result.score == 100
    assert result.total_dependencies == 2
    assert not any("pyproject" in warning for warning in result.warnings)


def test_export_includes_language_quality_matrix(tmp_path: Path) -> None:
    """Markdown/HTML exports must expose language-level evidence, not only one total."""
    (tmp_path / "server.rs").write_text("fn main() { println!(\"hello\"); }\n", encoding="utf-8")
    report = analyze_repository(tmp_path)

    markdown = ReportGenerator(tmp_path / "reports").to_markdown(report)
    html = ReportGenerator(tmp_path / "reports").to_html(report)

    assert "## Language Quality Breakdown" in markdown
    assert "Rust" in markdown
    assert "Language Quality Breakdown" in html
