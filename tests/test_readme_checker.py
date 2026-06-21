from pathlib import Path

from devpilot.readme_checker import ReadmeChecker
from devpilot.scanner import RepositoryScanner


COMPLETE_README = """# Demo Project

## Overview
This is a complete description for a professional repository. It explains why the project exists, who should use it, and how the tool helps developers improve their GitHub portfolio with clear analysis and actionable recommendations.

## Features
- Fast scan

## Installation
```bash
pip install -e .
```

## Usage
```bash
python run.py .
```

## Screenshots
![demo](docs/demo.png)

## Tech Stack
Python, pathlib, ast, dataclasses, Streamlit, GitPython, and pytest are used to build the analyzer, dashboard, GitHub clone support, and automated tests.

## Project Structure
```text
src/demo
```

## Roadmap
- Add more features.

## License
MIT License

## Contact
Author email and GitHub profile are listed here so users and recruiters can contact the maintainer, report issues, or request improvements for the tool.
"""


def test_readme_checker_scores_complete_readme(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(COMPLETE_README, encoding="utf-8")

    scan = RepositoryScanner(tmp_path).scan()
    result = ReadmeChecker(scan).analyze()

    assert result.found is True
    assert result.score >= 90
    assert not result.missing_sections


def test_readme_checker_reports_missing_readme(tmp_path: Path) -> None:
    scan = RepositoryScanner(tmp_path).scan()

    result = ReadmeChecker(scan).analyze()

    assert result.found is False
    assert result.score == 0
    assert "project title" in result.missing_sections
