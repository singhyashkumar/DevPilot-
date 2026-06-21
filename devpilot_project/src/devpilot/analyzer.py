"""Structure, testing, and multi-language maintainability analyzers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from devpilot.language_support import is_generated_source, is_test_file
from devpilot.models import ScanResult, StructureResult, TestingResult
from devpilot.utils import relative_posix, safe_read_text


class ProjectStructureAnalyzer:
    """Analyze whether a repository has a professional, language-neutral layout."""

    def __init__(self, scan: ScanResult) -> None:
        self.scan = scan

    def analyze(self) -> StructureResult:
        """Score the project layout and return actionable improvements."""
        if self.scan.total_files == 0:
            return StructureResult(
                score=0,
                issues=["Repository folder is empty"],
                suggestions=["Add source code, README, dependency manifest, and tests."],
            )
        score = 100
        good: list[str] = []
        issues: list[str] = []
        suggestions: list[str] = []
        for check in self._checks():
            if check.passed:
                good.append(check.good_message)
            else:
                score -= check.penalty
                issues.append(check.issue_message)
                suggestions.append(check.suggestion)
        return StructureResult(score=max(score, 0), good=good, issues=issues, suggestions=suggestions)

    def _checks(self) -> list["_StructureCheck"]:
        """Build consistent repository checks for every language ecosystem."""
        small_project = self.scan.source_file_count <= 2
        return [
            _StructureCheck(
                bool(self.scan.readme_file),
                "README file found",
                "README file is missing",
                16,
                "Add README.md with description, installation, usage, screenshots, roadmap, and license.",
            ),
            _StructureCheck(
                bool(self.scan.src_dirs) or small_project,
                "Source folder or compact project structure found",
                "No clear src/, app/, lib/, client/, or server/ folder found",
                12,
                "Move application code into a clear src/, app/, lib/, client/, or server/ area.",
            ),
            _StructureCheck(
                self.scan.has_dependency_file or self.scan.source_file_count == 0,
                "Dependency/build manifest found",
                "No common dependency or build manifest found",
                12,
                "Add package.json, pyproject.toml, go.mod, Cargo.toml, pom.xml, build.gradle, or composer.json.",
            ),
            _StructureCheck(
                bool(self.scan.test_dirs or self.scan.test_files),
                "Tests folder or test files found",
                "tests/ folder or test files are missing",
                14,
                "Add automated tests using your ecosystem's standard framework.",
            ),
            _StructureCheck(
                bool(self.scan.docs_dirs),
                "Documentation folder found",
                "docs/ folder is missing",
                8,
                "Add docs/ for architecture, usage, screenshots, and roadmap.",
            ),
            _StructureCheck(
                bool(self.scan.license_file),
                "License file found",
                "LICENSE file is missing",
                8,
                "Add an MIT, Apache-2.0, or suitable open-source license.",
            ),
            _StructureCheck(
                any(path.name == ".gitignore" for path in self.scan.all_files),
                ".gitignore file found",
                ".gitignore file is missing",
                8,
                "Add .gitignore to avoid committing dependencies, build output, caches, and secrets.",
            ),
            _StructureCheck(
                bool(self.scan.github_workflow_files),
                "GitHub Actions workflow found",
                "GitHub Actions workflow is missing",
                6,
                "Add CI to run tests, linting, type checks, or builds automatically.",
            ),
        ]


@dataclass(slots=True)
class _StructureCheck:
    passed: bool
    good_message: str
    issue_message: str
    penalty: int
    suggestion: str


class TestingAnalyzer:
    """Estimate test readiness across Python, JS/TS, JVM, Go, Rust, PHP, Ruby, and more."""

    __test__ = False

    FRAMEWORKS: dict[str, tuple[str, ...]] = {
        "pytest": ("pytest", "def test_"),
        "unittest": ("unittest", "TestCase"),
        "Jest / Vitest": ("jest", "vitest", "describe(", "test(", "it("),
        "JUnit / TestNG": ("@Test", "org.junit", "testng"),
        "Go testing": ("func Test", '"testing"'),
        "Rust test": ("#[test]", "#[cfg(test)]"),
        "PHPUnit": ("PHPUnit", "extends TestCase"),
        "RSpec / Minitest": ("RSpec.describe", "Minitest::Test"),
        "xUnit / NUnit": ("[Fact]", "[Test]", "xunit", "nunit"),
        "Swift XCTest": ("XCTestCase", "XCTAssert"),
        "Dart test": ("package:test", "group(", "test("),
    }

    def __init__(self, scan: ScanResult) -> None:
        self.scan = scan

    def analyze(self) -> TestingResult:
        """Score the test setup without assuming every project uses pytest."""
        score = 100
        issues: list[str] = []
        suggestions: list[str] = []
        test_files = [relative_posix(path, self.scan.root_path) for path in self.scan.test_files]
        frameworks = self._detect_test_frameworks()
        pytest_detected = "pytest" in frameworks
        unittest_detected = "unittest" in frameworks
        score -= self._test_presence_penalty(issues, suggestions)
        score -= self._framework_penalty(frameworks, issues, suggestions)
        missing_targets = self._missing_test_targets(test_files)
        if missing_targets:
            score -= min(25, len(missing_targets) * 3)
            issues.append(f"{len(missing_targets)} production source files may not have matching tests")
            suggestions.append("Add focused tests for the important modules, routes, services, and utilities listed in missing test targets.")
        return TestingResult(
            max(score, 0),
            len(self.scan.test_files),
            test_files,
            pytest_detected,
            unittest_detected,
            missing_targets[:20],
            issues,
            suggestions,
            frameworks_detected=frameworks,
        )

    def _detect_test_frameworks(self) -> list[str]:
        """Detect common framework markers from tests and dependency manifests."""
        combined = "\n".join(safe_read_text(path) for path in [*self.scan.test_files, *self.scan.dependency_files])
        lowered = combined.lower()
        detected: list[str] = []
        for framework, markers in self.FRAMEWORKS.items():
            if any(marker.lower() in lowered for marker in markers):
                detected.append(framework)
        return detected

    def _test_presence_penalty(self, issues: list[str], suggestions: list[str]) -> int:
        """Return a fair penalty based on project size and test presence."""
        if not self.scan.source_file_count:
            return 0
        if not self.scan.test_dirs and not self.scan.test_files:
            issues.append("No tests/ folder or recognized test files found")
            suggestions.append("Create a test suite with the standard framework for this stack (for example pytest, Jest/Vitest, JUnit, Go testing, Rust test, or xUnit).")
            return 55
        if not self.scan.test_files:
            issues.append("Test directory exists but no recognizable source test files were found")
            suggestions.append("Use conventional test filenames such as *.test.ts, *_test.go, Test*.java, test_*.py, or *Spec.cs.")
            return 40
        source_count = max(1, len(self._source_files_requiring_tests()))
        if source_count >= 3 and len(self.scan.test_files) < max(1, source_count // 3):
            issues.append("Test file count is low compared with production source files")
            suggestions.append("Increase coverage around core modules, public APIs, error paths, and business logic.")
            return 16
        return 0

    @staticmethod
    def _framework_penalty(frameworks: list[str], issues: list[str], suggestions: list[str]) -> int:
        """Return a modest penalty only when no common framework is visible."""
        if frameworks:
            return 0
        issues.append("No recognizable automated-test framework marker detected")
        suggestions.append("Document the test command and use an established framework for the repository's language.")
        return 10

    def _missing_test_targets(self, test_files: list[str]) -> list[str]:
        """Find production modules with no obvious test-name match, conservatively."""
        test_text = "\n".join(test_files).lower()
        missing: list[str] = []
        for module in self._source_files_requiring_tests():
            normalized_stem = module.stem.lower().replace("-", "_")
            if normalized_stem not in test_text:
                missing.append(relative_posix(module, self.scan.root_path))
        return missing

    def _source_files_requiring_tests(self) -> list[Path]:
        """Return source files where a test match is generally expected."""
        excluded_stems = {"__init__", "main", "index", "models", "types", "constants", "config"}
        candidates: list[Path] = []
        for path in self.scan.source_files:
            parts = path.relative_to(self.scan.root_path).parts
            if is_test_file(path, self.scan.root_path) or is_generated_source(path, self.scan.root_path):
                continue
            if (
                path.name in {"run.py", "serve.py"}
                or path.stem.lower() in excluded_stems
                or "dashboard" in parts
                or "static" in parts
            ):
                continue
            candidates.append(path)
        return candidates




# Re-export preserves the original public import path: devpilot.analyzer.CodeQualityAnalyzer.
from devpilot.code_quality import CodeQualityAnalyzer

__all__ = ["CodeQualityAnalyzer", "ProjectStructureAnalyzer", "TestingAnalyzer"]
# Make the re-export visible to the Python AST quality check as intentional public API.
_ = CodeQualityAnalyzer
