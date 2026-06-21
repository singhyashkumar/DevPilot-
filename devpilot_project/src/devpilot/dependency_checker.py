"""Cross-ecosystem dependency health checker for DevPilot."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from devpilot.models import DependencyResult, ScanResult
from devpilot.utils import normalize_package_name, relative_posix, safe_read_text


class DependencyChecker:
    """Analyze common Python, Node, JVM, Go, Rust, PHP, Ruby, .NET, and Dart manifests."""

    PIN_OPERATORS = ("==", ">=", "<=", "~=", "!=", "===", "@")

    def __init__(self, scan: ScanResult) -> None:
        self.scan = scan

    def analyze(self) -> DependencyResult:
        """Build a reasonable dependency health score without Python-only penalties."""
        files_found = [relative_posix(path, self.scan.root_path) for path in self.scan.dependency_files]
        dependencies: list[str] = []
        unpinned: list[str] = []
        parse_warnings: list[str] = []
        for path in self.scan.dependency_files:
            parsed, parsed_unpinned, warning = self._parse_manifest(path)
            dependencies.extend(parsed)
            unpinned.extend(parsed_unpinned)
            if warning:
                parse_warnings.append(warning)

        normalized = [normalize_package_name(dep) for dep in dependencies if normalize_package_name(dep)]
        duplicates = sorted(name for name, count in Counter(normalized).items() if count > 1)
        unique_unpinned = sorted(dict.fromkeys(unpinned))

        score = 100
        warnings: list[str] = list(parse_warnings)
        if self.scan.source_file_count and not files_found:
            score -= 65
            warnings.append("No common dependency or build manifest found")
        if duplicates:
            score -= min(20, len(duplicates) * 5)
            warnings.append(f"Duplicate dependencies found: {', '.join(duplicates[:8])}")
        if unique_unpinned:
            score -= min(20, len(unique_unpinned) * 3)
            warnings.append(f"{len(unique_unpinned)} parsed dependencies have no clear version or revision")
        if len(dependencies) > 100:
            score -= 10
            warnings.append("Dependency list is very large; verify unused or duplicated packages")
        if self.scan.python_file_count and self.scan.requirements_file and not self.scan.pyproject_file:
            score -= 5
            warnings.append("Python requirements.txt found without pyproject.toml; consider modern packaging metadata")

        return DependencyResult(
            score=max(score, 0),
            files_found=files_found,
            total_dependencies=len(dependencies),
            dependencies=dependencies,
            unpinned_dependencies=unique_unpinned,
            duplicate_dependencies=duplicates,
            warnings=warnings,
        )

    def _parse_manifest(self, path: Path) -> tuple[list[str], list[str], str | None]:
        """Parse a recognized manifest conservatively; return no warning when parsing is unsupported."""
        name = path.name.lower()
        text = safe_read_text(path)
        if name == "requirements.txt":
            dependencies = self._parse_requirements(text)
            return dependencies, [dep for dep in dependencies if not self._is_pinned(dep)], None
        if name == "pyproject.toml":
            dependencies = self._parse_pyproject_dependencies(text)
            return dependencies, [dep for dep in dependencies if not self._is_pinned(dep)], None
        if name == "package.json":
            return self._parse_package_json(text)
        if name == "go.mod":
            dependencies = self._parse_go_mod(text)
            return dependencies, [dep for dep in dependencies if " v" not in dep], None
        if name == "cargo.toml":
            dependencies = self._parse_toml_dependency_section(text)
            return dependencies, [dep for dep in dependencies if "=" not in dep], None
        if name == "composer.json":
            return self._parse_composer_json(text)
        if name in {"gemfile", "mix.exs", "pubspec.yaml"}:
            return self._parse_line_dependencies(text, name)
        if name in {"pom.xml", "build.gradle", "build.gradle.kts"}:
            return self._parse_jvm_dependencies(text, name)
        if path.suffix.lower() in {".csproj", ".fsproj"}:
            return self._parse_dotnet_dependencies(text)
        return [], [], None

    @staticmethod
    def _parse_requirements(text: str) -> list[str]:
        deps: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("-"):
                continue
            deps.append(stripped.split("#", 1)[0].strip())
        return deps

    @staticmethod
    def _parse_pyproject_dependencies(text: str) -> list[str]:
        deps: list[str] = []
        in_dependencies_array = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("dependencies") and "[" in stripped:
                in_dependencies_array = True
                deps.extend(re.findall(r"['\"]([^'\"]+)['\"]", stripped))
                if "]" in stripped:
                    in_dependencies_array = False
                continue
            if in_dependencies_array:
                deps.extend(re.findall(r"['\"]([^'\"]+)['\"]", stripped))
                if "]" in stripped:
                    in_dependencies_array = False
        return deps

    @staticmethod
    def _parse_package_json(text: str) -> tuple[list[str], list[str], str | None]:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return [], [], "package.json could not be parsed as valid JSON"
        sections = ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies")
        dependencies: list[str] = []
        unpinned: list[str] = []
        for section in sections:
            values = data.get(section, {})
            if not isinstance(values, dict):
                continue
            for name, version in values.items():
                entry = f"{name}@{version}"
                dependencies.append(entry)
                if not isinstance(version, str) or version.strip() in {"", "*", "latest"}:
                    unpinned.append(entry)
        return dependencies, unpinned, None

    @staticmethod
    def _parse_go_mod(text: str) -> list[str]:
        return [f"{module} {version}" for module, version in re.findall(r"^\s*([\w./-]+)\s+(v[^\s]+)", text, re.MULTILINE)]

    @staticmethod
    def _parse_toml_dependency_section(text: str) -> list[str]:
        deps: list[str] = []
        in_section = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("["):
                in_section = stripped.lower().startswith("[dependencies")
                continue
            if in_section and "=" in stripped and not stripped.startswith("#"):
                deps.append(stripped)
        return deps

    @staticmethod
    def _parse_composer_json(text: str) -> tuple[list[str], list[str], str | None]:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return [], [], "composer.json could not be parsed as valid JSON"
        dependencies: list[str] = []
        unpinned: list[str] = []
        for section in ("require", "require-dev"):
            for name, version in data.get(section, {}).items():
                entry = f"{name}@{version}"
                dependencies.append(entry)
                if str(version).strip() in {"", "*", "dev-master"}:
                    unpinned.append(entry)
        return dependencies, unpinned, None

    @staticmethod
    def _parse_line_dependencies(text: str, manifest_name: str) -> tuple[list[str], list[str], str | None]:
        if manifest_name == "gemfile":
            deps = re.findall(r"^\s*gem\s+['\"]([^'\"]+)['\"](?:\s*,\s*['\"]([^'\"]+)['\"])?", text, re.MULTILINE)
            values = [f"{name}@{version or ''}" for name, version in deps]
            return values, [entry for entry in values if entry.endswith("@")], None
        if manifest_name == "pubspec.yaml":
            values = re.findall(r"^\s{2,}([\w-]+):\s*([^\n#]+)?", text, re.MULTILINE)
            deps = [f"{name}@{version.strip() if version else ''}" for name, version in values if name not in {"sdk", "flutter"}]
            return deps, [entry for entry in deps if entry.endswith("@") or entry.endswith("@any")], None
        # mix.exs has richer Elixir syntax; flag detected dependency calls without pretending a precise version parser.
        deps = [f"{name}@{version}" for name, version in re.findall(r"\{:\s*([\w_]+)\s*,\s*\"([^\"]+)\"", text)]
        return deps, [], None

    @staticmethod
    def _parse_jvm_dependencies(text: str, manifest_name: str) -> tuple[list[str], list[str], str | None]:
        if manifest_name == "pom.xml":
            values = re.findall(r"<dependency>.*?<artifactId>([^<]+)</artifactId>.*?(?:<version>([^<]+)</version>)?.*?</dependency>", text, re.DOTALL)
            deps = [f"{name}@{version or ''}" for name, version in values]
            return deps, [entry for entry in deps if entry.endswith("@")], None
        values = re.findall(r"(?:implementation|api|testImplementation|compileOnly)\s*[('(\"]+([^'\")]+)", text)
        deps = [value for value in values]
        return deps, [entry for entry in deps if entry.count(":") < 2], None

    @staticmethod
    def _parse_dotnet_dependencies(text: str) -> tuple[list[str], list[str], str | None]:
        values = re.findall(r"<PackageReference\s+Include=\"([^\"]+)\"(?:\s+Version=\"([^\"]+)\")?", text)
        deps = [f"{name}@{version or ''}" for name, version in values]
        return deps, [entry for entry in deps if entry.endswith("@")], None

    @classmethod
    def _is_pinned(cls, requirement: str) -> bool:
        if requirement.startswith(("git+", "http://", "https://")):
            return True
        return any(operator in requirement for operator in cls.PIN_OPERATORS)
