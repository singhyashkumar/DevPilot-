"""Typed result models used by DevPilot analyzers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ScanResult:
    """Repository inventory shared by every analyzer."""

    repository_name: str
    root_path: Path
    total_files: int
    python_files: list[Path]
    source_files: list[Path]
    language_files: dict[str, list[Path]]
    dependency_files: list[Path]
    readme_file: Path | None
    requirements_file: Path | None
    pyproject_file: Path | None
    pipfile: Path | None
    poetry_lock: Path | None
    env_files: list[Path]
    test_files: list[Path]
    test_dirs: list[Path]
    docs_dirs: list[Path]
    config_files: list[Path]
    license_file: Path | None
    github_workflow_files: list[Path]
    src_dirs: list[Path]
    all_files: list[Path]

    @property
    def python_file_count(self) -> int:
        """Return the number of Python files, including tests."""
        return len(self.python_files)

    @property
    def source_file_count(self) -> int:
        """Return all supported code and web-source files."""
        return len(self.source_files)

    @property
    def language_counts(self) -> dict[str, int]:
        """Return language file counts in a serialization-friendly format."""
        return {language: len(files) for language, files in self.language_files.items()}

    @property
    def has_tests(self) -> bool:
        return bool(self.test_files or self.test_dirs)

    @property
    def has_dependency_file(self) -> bool:
        return bool(self.dependency_files)


@dataclass(slots=True, frozen=True)
class WorkloadEstimate:
    """Approximate work needed for a DevPilot audit."""

    estimated_seconds: int
    lower_seconds: int
    upper_seconds: int
    total_files: int
    python_files: int
    analyzable_python_files: int
    total_size_bytes: int
    confidence: str
    is_remote_placeholder: bool = False
    source_files: int = 0
    analyzable_source_files: int = 0

    @property
    def is_long_running(self) -> bool:
        """Return whether a countdown is useful for this audit."""
        return self.estimated_seconds >= 15


@dataclass(slots=True, frozen=True)
class AnalysisProgress:
    """One safe progress update emitted by the analysis engine."""

    phase: str
    label: str
    percent: int
    estimate_seconds: int | None = None


@dataclass(slots=True)
class AnalysisTiming:
    """Timing information saved with a completed analysis report."""

    estimated_seconds: int = 0
    actual_seconds: float = 0.0
    confidence: str = "calibrated"


@dataclass(slots=True)
class AnalysisPreflight:
    """Local pre-scan information used to show timing before analysis begins."""

    source: str
    scan: ScanResult | None
    estimate: WorkloadEstimate
    is_remote: bool


@dataclass(slots=True)
class StructureResult:
    score: int
    good: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CodeIssue:
    file: str
    message: str
    severity: str = "medium"
    language: str | None = None


@dataclass(slots=True)
class LanguageQualityResult:
    """Maintainability result for one programming or web-source language."""

    language: str
    score: int
    file_count: int
    total_lines: int
    total_functions: int
    comment_lines: int
    issues: list[CodeIssue] = field(default_factory=list)
    detected: bool = True

    @property
    def comment_ratio(self) -> float:
        """Return the percentage of all source lines that are comments."""
        return 0.0 if self.total_lines == 0 else self.comment_lines / self.total_lines


@dataclass(slots=True)
class CodeQualityResult:
    score: int
    total_lines: int
    total_functions: int
    long_files: list[str] = field(default_factory=list)
    long_functions: list[str] = field(default_factory=list)
    unused_imports: list[str] = field(default_factory=list)
    missing_docstrings: list[str] = field(default_factory=list)
    missing_type_hints: list[str] = field(default_factory=list)
    empty_except_blocks: list[str] = field(default_factory=list)
    print_statements: list[str] = field(default_factory=list)
    deep_nesting: list[str] = field(default_factory=list)
    poor_names: list[str] = field(default_factory=list)
    repeated_blocks: list[str] = field(default_factory=list)
    syntax_errors: list[str] = field(default_factory=list)
    issues: list[CodeIssue] = field(default_factory=list)
    analyzed_files: int = 0
    is_applicable: bool = True
    not_applicable_reason: str | None = None
    language_breakdown: list[LanguageQualityResult] = field(default_factory=list)
    analyzed_languages: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ReadmeResult:
    score: int
    found: bool
    path: str | None
    word_count: int
    present_sections: list[str] = field(default_factory=list)
    missing_sections: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


@dataclass(slots=True)
class DependencyResult:
    score: int
    files_found: list[str] = field(default_factory=list)
    total_dependencies: int = 0
    dependencies: list[str] = field(default_factory=list)
    unpinned_dependencies: list[str] = field(default_factory=list)
    duplicate_dependencies: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TestingResult:
    score: int
    test_files_count: int
    test_files: list[str] = field(default_factory=list)
    pytest_detected: bool = False
    unittest_detected: bool = False
    missing_test_targets: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    frameworks_detected: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SecurityResult:
    score: int
    warnings: list[str] = field(default_factory=list)
    risky_files: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ScoreBreakdown:
    overall_score: int
    grade: str
    strong_points: list[str]
    weak_points: list[str]
    top_issues: list[str]
    roadmap: list[str]
    weights: dict[str, float]


@dataclass(slots=True)
class RepositoryReport:
    repository_name: str
    language: str
    total_files: int
    python_files: int
    source_files: int
    languages: dict[str, int]
    structure: StructureResult
    code_quality: CodeQualityResult
    readme: ReadmeResult
    dependencies: DependencyResult
    testing: TestingResult
    security: SecurityResult
    score: ScoreBreakdown
    source: str
    analysis_timing: AnalysisTiming = field(default_factory=AnalysisTiming)

    def as_dict(self) -> dict[str, Any]:
        """Return a serializable representation of a complete repository report."""
        from dataclasses import asdict

        return asdict(self)
