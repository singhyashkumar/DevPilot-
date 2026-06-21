"""Tests for supported language and test-file detection helpers."""

from pathlib import Path

from devpilot.language_support import detect_language, is_test_file


def test_language_support_detects_common_extensions() -> None:
    """The support registry should recognize major backend and frontend languages."""
    assert detect_language(Path("app.tsx")) == "TypeScript"
    assert detect_language(Path("server.go")) == "Go"
    assert detect_language(Path("Main.java")) == "Java"
    assert detect_language(Path("style.css")) == "CSS"


def test_language_support_recognizes_common_test_names() -> None:
    """Cross-language test conventions should be detected before testing analysis."""
    assert is_test_file(Path("tests/api.test.ts")) is True
    assert is_test_file(Path("pkg/worker_test.go")) is True
    assert is_test_file(Path("src/MainTest.java")) is True
