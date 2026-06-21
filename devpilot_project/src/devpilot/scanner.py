"""Repository scanner for DevPilot."""

from __future__ import annotations

import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path

from devpilot.language_support import detect_language, is_source_file, is_test_file
from devpilot.models import ScanResult
from devpilot.utils import is_ignored_path, looks_like_github_url


# Ecosystem dependency manifests. They are used for fair cross-language structure
# and dependency checks; parsing remains conservative in dependency_checker.py.
DEPENDENCY_MANIFESTS = {
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lockb",
    "go.mod",
    "cargo.toml",
    "cargo.lock",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "gradle.properties",
    "composer.json",
    "composer.lock",
    "gemfile",
    "gemfile.lock",
    "mix.exs",
    "package.swift",
    "podfile",
    "pubspec.yaml",
    "pubspec.lock",
    "*.csproj",
    "*.fsproj",
    "vcpkg.json",
    "conanfile.txt",
    "conanfile.py",
}


class RepositoryScanner:
    """Scan a local repository folder and detect important project files."""

    def __init__(self, root_path: str | Path) -> None:
        """Create a scanner for an existing repository directory."""
        self.root_path = Path(root_path).expanduser().resolve()
        self._validate_root_path()

    def scan(self) -> ScanResult:
        """Return a complete inventory of important files and folders."""
        state = _ScanState(root_path=self.root_path)
        for path in self.root_path.rglob("*"):
            relative = path.relative_to(self.root_path)
            if is_ignored_path(relative):
                continue
            if path.is_dir():
                state.register_directory(path)
            else:
                state.register_file(path)
        return state.to_result()

    def _validate_root_path(self) -> None:
        """Ensure the given repository path exists and is a folder."""
        if not self.root_path.exists():
            raise FileNotFoundError(f"Repository path does not exist: {self.root_path}")
        if not self.root_path.is_dir():
            raise NotADirectoryError(f"Repository path is not a folder: {self.root_path}")


class _ScanState:
    """Mutable scanner state used to keep RepositoryScanner.scan small."""

    def __init__(self, root_path: Path) -> None:
        """Initialize empty scanner buckets."""
        self.root_path = root_path
        self.all_files: list[Path] = []
        self.python_files: list[Path] = []
        self.source_files: list[Path] = []
        self.language_files: defaultdict[str, list[Path]] = defaultdict(list)
        self.dependency_files: list[Path] = []
        self.env_files: list[Path] = []
        self.test_files: list[Path] = []
        self.test_dirs: list[Path] = []
        self.docs_dirs: list[Path] = []
        self.config_files: list[Path] = []
        self.github_workflow_files: list[Path] = []
        self.src_dirs: list[Path] = []
        self.readme_file: Path | None = None
        self.requirements_file: Path | None = None
        self.pyproject_file: Path | None = None
        self.pipfile: Path | None = None
        self.poetry_lock: Path | None = None
        self.license_file: Path | None = None

    def register_directory(self, path: Path) -> None:
        """Record known project directory types."""
        name_lower = path.name.lower()
        if name_lower in {"tests", "test", "__tests__", "spec", "specs"}:
            self.test_dirs.append(path)
        elif name_lower in {"docs", "documentation"}:
            self.docs_dirs.append(path)
        elif name_lower in {"src", "app", "apps", "package", "lib", "server", "client"}:
            self.src_dirs.append(path)

    def register_file(self, path: Path) -> None:
        """Record a file and classify it into useful repository buckets."""
        self.all_files.append(path)
        relative = path.relative_to(self.root_path)
        name_lower = path.name.lower()
        self._register_source_file(path, relative)
        self._register_named_file(path, name_lower)
        self._register_config_file(path, name_lower)
        self._register_dependency_file(path, name_lower)
        self._register_github_workflow(path, relative)

    def to_result(self) -> ScanResult:
        """Convert collected state into the public ScanResult model."""
        ordered_languages = {
            language: sorted(paths)
            for language, paths in sorted(self.language_files.items(), key=lambda item: item[0])
        }
        return ScanResult(
            repository_name=self.root_path.name,
            root_path=self.root_path,
            total_files=len(self.all_files),
            python_files=sorted(self.python_files),
            source_files=sorted(self.source_files),
            language_files=ordered_languages,
            dependency_files=sorted(set(self.dependency_files)),
            readme_file=self.readme_file,
            requirements_file=self.requirements_file,
            pyproject_file=self.pyproject_file,
            pipfile=self.pipfile,
            poetry_lock=self.poetry_lock,
            env_files=sorted(self.env_files),
            test_files=sorted(set(self.test_files)),
            test_dirs=sorted(set(self.test_dirs)),
            docs_dirs=sorted(self.docs_dirs),
            config_files=sorted(self.config_files),
            license_file=self.license_file,
            github_workflow_files=sorted(self.github_workflow_files),
            src_dirs=sorted(self.src_dirs),
            all_files=sorted(self.all_files),
        )

    def _register_source_file(self, path: Path, relative: Path) -> None:
        """Classify source files across supported programming and web languages."""
        if not is_source_file(path):
            return
        language = detect_language(path)
        if language is None:
            return
        self.source_files.append(path)
        self.language_files[language].append(path)
        if language == "Python":
            self.python_files.append(path)
        if is_test_file(path, self.root_path):
            self.test_files.append(path)

    def _register_named_file(self, path: Path, name_lower: str) -> None:
        """Detect project-level named files like README and LICENSE."""
        if name_lower.startswith("readme") and path.suffix.lower() in {".md", ".rst", ".txt", ""}:
            self.readme_file = self.readme_file or path
            return
        named_targets = {
            "requirements.txt": "requirements_file",
            "pyproject.toml": "pyproject_file",
            "pipfile": "pipfile",
            "poetry.lock": "poetry_lock",
        }
        if name_lower in named_targets:
            setattr(self, named_targets[name_lower], path)
            return
        if name_lower.startswith(".env"):
            self.env_files.append(path)
            return
        if name_lower in {"license", "license.md", "license.txt", "copying"}:
            self.license_file = path

    def _register_config_file(self, path: Path, name_lower: str) -> None:
        """Detect common configuration files."""
        if name_lower.startswith(".env"):
            return
        if path.suffix.lower() in {".toml", ".ini", ".cfg", ".yaml", ".yml", ".json", ".xml", ".gradle"}:
            self.config_files.append(path)

    def _register_dependency_file(self, path: Path, name_lower: str) -> None:
        """Register Python and non-Python dependency/build manifests."""
        normalized = name_lower
        if normalized in DEPENDENCY_MANIFESTS or path.suffix.lower() in {".csproj", ".fsproj"}:
            self.dependency_files.append(path)
        elif normalized in {"requirements.txt", "pyproject.toml", "pipfile", "poetry.lock"}:
            self.dependency_files.append(path)

    def _register_github_workflow(self, path: Path, relative: Path) -> None:
        """Detect GitHub Actions workflow files."""
        if ".github" in relative.parts and "workflows" in relative.parts:
            self.github_workflow_files.append(path)


def clone_github_repository(url: str) -> Path:
    """Clone a public GitHub repository into a temporary folder."""
    if not looks_like_github_url(url):
        raise ValueError("Only clean public GitHub repository URLs are supported.")
    temp_dir = Path(tempfile.mkdtemp(prefix="devpilot_repo_"))
    clone_dir = temp_dir / "repo"
    _clone_with_gitpython_or_cli(url, clone_dir)
    return clone_dir


def _clone_with_gitpython_or_cli(url: str, clone_dir: Path) -> None:
    """Clone using GitPython first and system git as a fallback."""
    try:
        from git import Repo  # type: ignore

        Repo.clone_from(url, clone_dir, depth=1)
    except Exception:
        result = subprocess.run(
            ["git", "clone", "--depth", "1", url, str(clone_dir)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(_clone_error_message(result.stderr)) from None


def _clone_error_message(stderr: str) -> str:
    """Build a user-friendly Git clone failure message."""
    details = stderr.strip() or "No error details returned by git."
    return "Could not clone GitHub repository. Install Git or check the repository URL.\n" f"Details: {details}"
