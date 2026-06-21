from pathlib import Path

from devpilot.analyzer import CodeQualityAnalyzer, ProjectStructureAnalyzer, TestingAnalyzer as DevPilotTestingAnalyzer
from devpilot.scanner import RepositoryScanner


def _create_project(tmp_path: Path) -> Path:
    project = tmp_path / "demo"
    (project / "src" / "demo").mkdir(parents=True)
    (project / "tests").mkdir(parents=True)
    (project / "docs").mkdir()
    (project / ".github" / "workflows").mkdir(parents=True)
    (project / "README.md").write_text("# Demo\n\n## Overview\nA demo project.", encoding="utf-8")
    (project / "requirements.txt").write_text("pytest>=8", encoding="utf-8")
    (project / "LICENSE").write_text("MIT", encoding="utf-8")
    (project / ".gitignore").write_text(".venv/", encoding="utf-8")
    (project / ".github" / "workflows" / "ci.yml").write_text("name: ci", encoding="utf-8")
    (project / "src" / "demo" / "scanner.py").write_text(
        '"""Demo module."""\n\ndef greet(name: str) -> str:\n    """Return a greeting."""\n    return f"Hi {name}"\n',
        encoding="utf-8",
    )
    (project / "tests" / "test_scanner.py").write_text(
        "from demo.scanner import greet\n\ndef test_greet() -> None:\n    assert greet('Yash') == 'Hi Yash'\n",
        encoding="utf-8",
    )
    return project


def test_structure_analyzer_scores_complete_project(tmp_path: Path) -> None:
    scan = RepositoryScanner(_create_project(tmp_path)).scan()

    result = ProjectStructureAnalyzer(scan).analyze()

    assert result.score == 100
    assert not result.issues


def test_testing_analyzer_detects_pytest_and_targets(tmp_path: Path) -> None:
    scan = RepositoryScanner(_create_project(tmp_path)).scan()

    result = DevPilotTestingAnalyzer(scan).analyze()

    assert result.score >= 90
    assert result.pytest_detected is True
    assert result.test_files_count == 1


def test_code_quality_analyzer_detects_long_function(tmp_path: Path) -> None:
    project = _create_project(tmp_path)
    long_body = "\n".join(f"    value_{index} = {index}" for index in range(90))
    (project / "src" / "demo" / "bad.py").write_text(
        f'def very_long_function() -> None:\n{long_body}\n',
        encoding="utf-8",
    )
    scan = RepositoryScanner(project).scan()

    result = CodeQualityAnalyzer(scan).analyze()

    assert result.score < 100
    assert result.long_functions


def test_testing_analyzer_excludes_static_dashboard_assets(tmp_path: Path) -> None:
    """Static HTML/CSS/JS assets should not be reported as missing unit-test targets."""
    (tmp_path / "static" / "js").mkdir(parents=True)
    (tmp_path / "static" / "css").mkdir(parents=True)
    (tmp_path / "static" / "js" / "app.js").write_text("export const ready = true;", encoding="utf-8")
    (tmp_path / "static" / "css" / "style.css").write_text("body { margin: 0; }", encoding="utf-8")
    (tmp_path / "serve.py").write_text("print('server')", encoding="utf-8")
    scan = RepositoryScanner(tmp_path).scan()
    result = DevPilotTestingAnalyzer(scan).analyze()
    assert result.missing_test_targets == []
