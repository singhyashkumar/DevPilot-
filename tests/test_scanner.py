from pathlib import Path

import pytest

from devpilot.scanner import RepositoryScanner, clone_github_repository


def test_scanner_detects_repository_files(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / "README.md").write_text("# Demo", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("pytest>=8", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'", encoding="utf-8")
    (tmp_path / "LICENSE").write_text("MIT", encoding="utf-8")
    (tmp_path / "src" / "app.py").write_text("def main() -> None:\n    pass\n", encoding="utf-8")
    (tmp_path / "tests" / "test_app.py").write_text("def test_app() -> None:\n    assert True\n", encoding="utf-8")
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("name: ci", encoding="utf-8")

    result = RepositoryScanner(tmp_path).scan()

    assert result.repository_name == tmp_path.name
    assert result.python_file_count == 2
    assert result.has_dependency_file is True
    assert result.has_tests is True
    assert result.readme_file is not None
    assert result.license_file is not None
    assert result.github_workflow_files


def test_scanner_rejects_missing_path(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing"

    with pytest.raises(FileNotFoundError):
        RepositoryScanner(missing_path)


def test_clone_github_repository_rejects_non_github_url() -> None:
    with pytest.raises(ValueError):
        clone_github_repository("https://example.com/not-a-repo")
