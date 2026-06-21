"""Focused tests for the public multi-language code-quality engine."""

from pathlib import Path

from devpilot.analyzer import CodeQualityAnalyzer
from devpilot.scanner import RepositoryScanner


def test_code_quality_engine_flags_empty_catch_in_typescript(tmp_path: Path) -> None:
    """TypeScript should receive language-aware findings without a Python AST dependency."""
    (tmp_path / "service.ts").write_text(
        "export function run(): void {\n  try { risky(); } catch (error) {}\n}\n",
        encoding="utf-8",
    )
    result = CodeQualityAnalyzer(RepositoryScanner(tmp_path).scan()).analyze()

    assert result.is_applicable is True
    assert result.analyzed_languages == ["TypeScript"]
    assert any("empty catch" in item.message for item in result.issues)


def test_code_quality_respects_documented_compact_asset_line_exemption(tmp_path: Path) -> None:
    """A deliberate visual asset exemption should not become a false maintainability penalty."""
    (tmp_path / "theme.css").write_text(
        "/* devpilot: allow-long-lines */\n" + (".x{" + "color:red;" * 30 + "}\n") * 3,
        encoding="utf-8",
    )

    result = CodeQualityAnalyzer(RepositoryScanner(tmp_path).scan()).analyze()

    assert not result.long_files
    assert not any("lines longer" in issue.message for issue in result.issues)
