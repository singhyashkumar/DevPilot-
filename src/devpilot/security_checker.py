"""Security warning scanner for DevPilot."""

from __future__ import annotations

import ast
import re

from devpilot.models import ScanResult, SecurityResult
from devpilot.utils import is_probably_text_file, relative_posix, safe_read_text


class SecurityChecker:
    """Find common beginner security mistakes in repository files."""

    SECRET_ASSIGNMENT_RE = re.compile(
        r"(?i)\b(password|passwd|pwd|token|secret|api[_-]?key|access[_-]?key|private[_-]?key)\b\s*[:=]\s*['\"][^'\"]{8,}['\"]"
    )
    AWS_KEY_RE = re.compile(r"AKIA[0-9A-Z]{16}")
    DATABASE_URL_RE = re.compile(r"(?i)(postgres|mysql|mongodb|redis)://[^\s'\"]+")
    PRIVATE_KEY_RE = re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----")
    GENERIC_RISK_PATTERNS = (
        (re.compile(r"\beval\s*\("), "uses dynamic eval()"),
        (re.compile(r"\bchild_process\.exec(?:Sync)?\s*\("), "executes a shell command through child_process"),
        (re.compile(r"\bRuntime\.getRuntime\(\)\.exec\s*\("), "executes an OS command through Runtime.exec"),
        (re.compile(r"\bProcess\.Start\s*\("), "starts an OS process without visible argument validation"),
        (re.compile(r"\bexec\s*\("), "uses dynamic exec()"),
    )

    def __init__(self, scan: ScanResult) -> None:
        self.scan = scan

    def analyze(self) -> SecurityResult:
        """Scan supported text source for secrets and high-signal unsafe execution patterns."""
        warnings: list[str] = []
        risky_files: set[str] = set()

        for env_file in self.scan.env_files:
            relative = relative_posix(env_file, self.scan.root_path)
            warnings.append(f".env-style file is present in repository: {relative}")
            risky_files.add(relative)

        for file_path in self.scan.all_files:
            if not is_probably_text_file(file_path):
                continue
            relative = relative_posix(file_path, self.scan.root_path)
            text = safe_read_text(file_path)
            if not text:
                continue

            for pattern, label in [
                (self.SECRET_ASSIGNMENT_RE, "possible hardcoded secret"),
                (self.AWS_KEY_RE, "possible AWS access key"),
                (self.DATABASE_URL_RE, "hardcoded database URL"),
                (self.PRIVATE_KEY_RE, "private key content"),
            ]:
                for match in pattern.finditer(text):
                    line = text.count("\n", 0, match.start()) + 1
                    warnings.append(f"{relative}:{line} contains {label}")
                    risky_files.add(relative)

            if file_path.suffix == ".py":
                for warning in self._scan_python_ast(text, relative):
                    warnings.append(warning)
                    risky_files.add(relative)
            else:
                for warning in self._scan_generic_risky_calls(text, relative, file_path.suffix.lower()):
                    warnings.append(warning)
                    risky_files.add(relative)

        score = 100
        if warnings:
            score -= min(80, len(warnings) * 10)
        high_risk_count = sum("private key" in warning or "AWS" in warning or ".env" in warning for warning in warnings)
        score -= min(25, high_risk_count * 8)

        return SecurityResult(score=max(score, 0), warnings=warnings[:100], risky_files=sorted(risky_files))

    @classmethod
    def _scan_generic_risky_calls(cls, text: str, relative: str, suffix: str) -> list[str]:
        """Find high-signal dynamic execution APIs in non-Python source files."""
        if suffix not in {".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".java", ".cs", ".php", ".rb", ".sh", ".ps1"}:
            return []
        warnings: list[str] = []
        for pattern, label in cls.GENERIC_RISK_PATTERNS:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                warnings.append(f"{relative}:{line} {label}")
                if len(warnings) >= 15:
                    return warnings
        return warnings

    @staticmethod
    def _scan_python_ast(text: str, relative: str) -> list[str]:
        warnings: list[str] = []
        try:
            tree = ast.parse(text, filename=relative)
        except SyntaxError:
            return warnings

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
                    warnings.append(f"{relative}:{node.lineno} uses unsafe {node.func.id}()")

                function_name = ""
                if isinstance(node.func, ast.Attribute):
                    function_name = node.func.attr
                elif isinstance(node.func, ast.Name):
                    function_name = node.func.id

                if function_name in {"run", "call", "Popen"}:
                    for keyword in node.keywords:
                        if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                            warnings.append(f"{relative}:{node.lineno} uses subprocess with shell=True")

        return warnings
