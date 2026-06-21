"""Command-line entry point, timing estimates, and analysis orchestration for DevPilot."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from time import perf_counter

from devpilot.analyzer import CodeQualityAnalyzer, ProjectStructureAnalyzer, TestingAnalyzer
from devpilot.dependency_checker import DependencyChecker
from devpilot.language_support import major_languages
from devpilot.models import (
    AnalysisPreflight,
    AnalysisProgress,
    AnalysisTiming,
    CodeQualityResult,
    DependencyResult,
    ReadmeResult,
    RepositoryReport,
    ScanResult,
    SecurityResult,
    StructureResult,
    TestingResult,
    WorkloadEstimate,
)
from devpilot.readme_checker import ReadmeChecker
from devpilot.report_generator import ReportGenerator
from devpilot.scanner import RepositoryScanner, clone_github_repository
from devpilot.score_engine import ScoreEngine
from devpilot.security_checker import SecurityChecker
from devpilot.timing import estimate_from_scan, format_duration, remote_placeholder_estimate
from devpilot.utils import looks_like_github_url, remove_tree

ProgressCallback = Callable[[AnalysisProgress], None]
AnalysisResults = tuple[
    StructureResult,
    CodeQualityResult,
    ReadmeResult,
    DependencyResult,
    TestingResult,
    SecurityResult,
]


def prepare_analysis(source: str | Path) -> AnalysisPreflight:
    """Pre-scan a local repository so the dashboard can show an honest ETA immediately.

    GitHub repositories cannot be sized without cloning, so they receive a clearly labelled
    initial range which is recalibrated as soon as cloning and scanning finishes.
    """
    source_text = str(source).strip()
    if looks_like_github_url(source_text):
        return AnalysisPreflight(
            source=source_text,
            scan=None,
            estimate=remote_placeholder_estimate(),
            is_remote=True,
        )
    repo_path = Path(source_text).expanduser().resolve()
    scan = RepositoryScanner(repo_path).scan()
    return AnalysisPreflight(
        source=str(repo_path),
        scan=scan,
        estimate=estimate_from_scan(scan),
        is_remote=False,
    )


def analyze_repository(
    source: str | Path,
    *,
    pre_scanned: ScanResult | None = None,
    estimated_seconds: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> RepositoryReport:
    """Analyze a local folder or public GitHub repository with optional progress events."""
    started_at = perf_counter()
    source_text = str(source).strip()
    _emit(progress_callback, "prepare", "Validating repository source", 4)
    cloned_parent: Path | None = None
    try:
        scan, source_label, cloned_parent = _load_repository_scan(source_text, pre_scanned, progress_callback)
        estimate = estimate_from_scan(scan)
        _emit_calibrated_progress(progress_callback, estimate.estimated_seconds)
        results = _run_analyzers(scan, progress_callback)
        report = _build_report(
            scan,
            source_label,
            results,
            estimate,
            estimated_seconds,
            started_at,
            progress_callback,
        )
        _emit(progress_callback, "complete", "Analysis complete", 100, report.analysis_timing.estimated_seconds)
        return report
    finally:
        if cloned_parent is not None:
            remove_tree(cloned_parent)


def _load_repository_scan(
    source_text: str,
    pre_scanned: ScanResult | None,
    callback: ProgressCallback | None,
) -> tuple[ScanResult, str, Path | None]:
    """Load a local scan or clone and scan a public GitHub repository."""
    if looks_like_github_url(source_text):
        _emit(callback, "clone", "Cloning GitHub repository", 10)
        repo_path = clone_github_repository(source_text)
        _emit(callback, "scan", "Mapping cloned repository files", 24)
        return RepositoryScanner(repo_path).scan(), source_text, repo_path.parent

    repo_path = Path(source_text).expanduser().resolve()
    scan = pre_scanned or RepositoryScanner(repo_path).scan()
    _emit(callback, "scan", "Repository map loaded", 22)
    return scan, str(repo_path), None


def _emit_calibrated_progress(callback: ProgressCallback | None, estimated_seconds: int) -> None:
    """Tell UI consumers when an audit ETA has been calculated from the actual source tree."""
    _emit(
        callback,
        "calibrate",
        f"Workload calibrated: about {format_duration(estimated_seconds)}",
        30,
        estimated_seconds,
    )


def _run_analyzers(scan: ScanResult, callback: ProgressCallback | None) -> AnalysisResults:
    """Run all repository analyzers in the order used by the live dashboard."""
    _emit(callback, "structure", "Reviewing repository structure", 38)
    structure = ProjectStructureAnalyzer(scan).analyze()
    _emit(callback, "code", "Auditing multi-language maintainability signals", 56)
    code_quality = CodeQualityAnalyzer(scan).analyze()
    _emit(callback, "readme", "Checking README and documentation coverage", 66)
    readme = ReadmeChecker(scan).analyze()
    _emit(callback, "dependencies", "Checking package dependency health", 74)
    dependencies = DependencyChecker(scan).analyze()
    _emit(callback, "testing", "Estimating test readiness", 82)
    testing = TestingAnalyzer(scan).analyze()
    _emit(callback, "security", "Scanning security-risk patterns", 90)
    security = SecurityChecker(scan).analyze()
    return structure, code_quality, readme, dependencies, testing, security


def _build_report(
    scan: ScanResult,
    source_label: str,
    results: AnalysisResults,
    estimate: WorkloadEstimate,
    requested_estimate: int | None,
    started_at: float,
    callback: ProgressCallback | None,
) -> RepositoryReport:
    """Build a score and final report from completed analyzer results."""
    structure, code_quality, readme, dependencies, testing, security = results
    _emit(callback, "score", "Synthesizing scores and improvement roadmap", 97)
    score = ScoreEngine().calculate(
        structure=structure,
        code_quality=code_quality,
        readme=readme,
        dependencies=dependencies,
        testing=testing,
        security=security,
    )
    return RepositoryReport(
        repository_name=scan.repository_name,
        language=_language_label(scan),
        total_files=scan.total_files,
        python_files=scan.python_file_count,
        source_files=scan.source_file_count,
        languages=scan.language_counts,
        structure=structure,
        code_quality=code_quality,
        readme=readme,
        dependencies=dependencies,
        testing=testing,
        security=security,
        score=score,
        source=source_label,
        analysis_timing=AnalysisTiming(
            estimated_seconds=requested_estimate or estimate.estimated_seconds,
            actual_seconds=perf_counter() - started_at,
            confidence=estimate.confidence,
        ),
    )


def cli() -> None:
    """Parse command-line arguments and run a DevPilot analysis."""
    parser = argparse.ArgumentParser(description="DevPilot — AI GitHub Repository Analyzer")
    parser.add_argument("source", help="Local repository folder path or public GitHub repository URL")
    parser.add_argument("--export", action="store_true", help="Export JSON, Markdown, and HTML reports")
    parser.add_argument("--output-dir", default="reports", help="Folder where exported reports will be saved")
    parser.add_argument("--json", action="store_true", help="Print full JSON report to terminal")
    args = parser.parse_args()

    preflight = prepare_analysis(args.source)
    print(f"Estimated audit time: {format_duration(preflight.estimate.estimated_seconds)}")
    report = analyze_repository(
        args.source,
        pre_scanned=preflight.scan,
        estimated_seconds=preflight.estimate.estimated_seconds,
    )
    _print_console_summary(report)

    if args.export:
        exported = ReportGenerator(args.output_dir).export_all(report)
        print("\nReports exported successfully:")
        for report_type, path in exported.items():
            print(f"- {report_type}: {path}")

    if args.json:
        print(json.dumps(report.as_dict(), indent=2, default=str))


def _emit(
    callback: ProgressCallback | None,
    phase: str,
    label: str,
    percent: int,
    estimate_seconds: int | None = None,
) -> None:
    """Send a progress event without making progress support mandatory."""
    if callback is not None:
        callback(AnalysisProgress(phase, label, percent, estimate_seconds))


def _language_label(scan: ScanResult) -> str:
    """Describe the dominant repository language mix without a Python-only assumption."""
    detected = major_languages(scan.language_files, limit=3)
    if not detected:
        return "No supported source detected"
    if len(detected) == 1:
        return detected[0][0]
    return " + ".join(f"{language} ({count})" for language, count in detected)


def _print_console_summary(report: RepositoryReport) -> None:
    """Print a compact, useful CLI report."""
    print("=" * 64)
    print("DevPilot Analysis Completed")
    print("=" * 64)
    print(f"Repository:      {report.repository_name}")
    print(f"Source:          {report.source}")
    print(f"Total Files:     {report.total_files}")
    print(f"Source Files:    {report.source_files}")
    print(f"Python Files:    {report.python_files}")
    print(f"Languages:       {report.language}")
    print(f"Analysis Time:   {format_duration(report.analysis_timing.actual_seconds)}")
    print(f"Overall Score:   {report.score.overall_score}/100")
    print(f"Grade:           {report.score.grade}")
    print("-" * 64)
    code_quality_text = f"{report.code_quality.score}/100" if report.code_quality.is_applicable else "N/A (no supported production source files)"
    print(f"Code Quality:    {code_quality_text}")
    if report.code_quality.is_applicable:
        language_scores = ", ".join(f"{item.language} {item.score}/100" for item in report.code_quality.language_breakdown)
        print(f"Language Scores: {language_scores}")
    print(f"Documentation:   {report.readme.score}/100")
    print(f"Testing:         {report.testing.score}/100")
    print(f"Security:        {report.security.score}/100")
    print(f"Dependencies:    {report.dependencies.score}/100")
    print(f"Structure:       {report.structure.score}/100")
    print("-" * 64)
    print("Top Issues:")
    for index, issue in enumerate(report.score.top_issues[:5], start=1):
        print(f"{index}. {issue}")
    print("-" * 64)
    print("Recommended Roadmap:")
    for index, item in enumerate(report.score.roadmap[:6], start=1):
        print(f"{index}. {item}")
    print("=" * 64)


if __name__ == "__main__":
    cli()
