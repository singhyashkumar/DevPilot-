from pathlib import Path

from devpilot.main import analyze_repository


def test_analyze_repository_for_minimal_project(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n\n## Overview\nSmall project", encoding="utf-8")
    (tmp_path / "main.py").write_text("def main() -> None:\n    pass\n", encoding="utf-8")

    report = analyze_repository(tmp_path)

    assert report.repository_name == tmp_path.name
    assert report.python_files == 1
    assert report.language == "Python"
