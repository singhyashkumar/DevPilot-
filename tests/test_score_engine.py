from pathlib import Path

from devpilot.main import analyze_repository
from devpilot.score_engine import ScoreEngine


def test_grade_boundaries() -> None:
    engine = ScoreEngine()

    assert engine.grade(95) == "Excellent"
    assert engine.grade(80) == "Good"
    assert engine.grade(65) == "Average"
    assert engine.grade(45) == "Needs Improvement"
    assert engine.grade(20) == "Poor"


def test_full_analysis_returns_score(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "README.md").write_text("# Demo\n\n## Overview\nDemo project", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("pytest>=8", encoding="utf-8")
    (tmp_path / "src" / "app.py").write_text(
        '"""App module."""\n\ndef add(a: int, b: int) -> int:\n    """Add two numbers."""\n    return a + b\n',
        encoding="utf-8",
    )
    (tmp_path / "tests" / "test_app.py").write_text("def test_app() -> None:\n    assert True\n", encoding="utf-8")

    report = analyze_repository(tmp_path)

    assert 0 <= report.score.overall_score <= 100
    assert report.repository_name == tmp_path.name
