from pathlib import Path

from devpilot.scanner import RepositoryScanner
from devpilot.security_checker import SecurityChecker


def test_security_checker_detects_env_and_eval(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("TOKEN=secret-value", encoding="utf-8")
    (tmp_path / "unsafe.py").write_text("def run(value: str) -> object:\n    return eval(value)\n", encoding="utf-8")

    scan = RepositoryScanner(tmp_path).scan()
    result = SecurityChecker(scan).analyze()

    assert result.score < 100
    assert any(".env-style" in warning for warning in result.warnings)
    assert any("eval" in warning for warning in result.warnings)


def test_security_checker_allows_clean_project(tmp_path: Path) -> None:
    (tmp_path / "safe.py").write_text("def add(a: int, b: int) -> int:\n    return a + b\n", encoding="utf-8")

    scan = RepositoryScanner(tmp_path).scan()
    result = SecurityChecker(scan).analyze()

    assert result.score == 100
    assert result.warnings == []
