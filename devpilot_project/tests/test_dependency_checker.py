from pathlib import Path

from devpilot.dependency_checker import DependencyChecker
from devpilot.scanner import RepositoryScanner


def test_dependency_checker_detects_duplicates_and_unpinned_packages(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("requests\nrequests==2.32.0\npytest>=8\n", encoding="utf-8")

    scan = RepositoryScanner(tmp_path).scan()
    result = DependencyChecker(scan).analyze()

    assert result.total_dependencies == 3
    assert "requests" in result.duplicate_dependencies
    assert result.unpinned_dependencies == ["requests"]
    assert result.score < 100


def test_dependency_checker_reads_pyproject_dependencies(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["streamlit>=1.36", "GitPython>=3.1"]\n',
        encoding="utf-8",
    )

    scan = RepositoryScanner(tmp_path).scan()
    result = DependencyChecker(scan).analyze()

    assert result.total_dependencies == 2
    assert result.score == 100
