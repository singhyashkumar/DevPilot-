from pathlib import Path

from devpilot.utils import looks_like_github_url, normalize_package_name, relative_posix, safe_read_text


def test_looks_like_github_url() -> None:
    assert looks_like_github_url("https://github.com/user/repo") is True
    assert looks_like_github_url("https://github.com/user/repo.git") is True
    assert looks_like_github_url("https://example.com/user/repo") is False


def test_normalize_package_name() -> None:
    assert normalize_package_name("Requests==2.32.0") == "requests"
    assert normalize_package_name("my_package[dev]>=1.0") == "my-package"


def test_safe_read_text_and_relative_posix(tmp_path: Path) -> None:
    file_path = tmp_path / "folder" / "demo.txt"
    file_path.parent.mkdir()
    file_path.write_text("hello", encoding="utf-8")

    assert safe_read_text(file_path) == "hello"
    assert relative_posix(file_path, tmp_path) == "folder/demo.txt"
