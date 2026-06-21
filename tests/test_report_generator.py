from pathlib import Path

from devpilot.main import analyze_repository
from devpilot.report_generator import ReportGenerator


def test_report_generator_exports_all_formats(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Demo\n\n## Overview\nDemo", encoding="utf-8")
    (tmp_path / "app.py").write_text("def main() -> None:\n    pass\n", encoding="utf-8")

    report = analyze_repository(tmp_path)
    output_dir = tmp_path / "reports"
    exported = ReportGenerator(output_dir).export_all(report, "demo_report")

    assert exported["json"].exists()
    assert exported["markdown"].exists()
    assert exported["html"].exists()
    assert "DevPilot Repository Report" in exported["markdown"].read_text(encoding="utf-8")
