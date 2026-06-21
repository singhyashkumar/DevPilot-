"""Cross-language maintainability engine used by DevPilot.

The module is intentionally a dedicated rules engine: it combines Python AST checks
with conservative language-aware source checks for other supported ecosystems.
"""

# devpilot: allow-long-file -- the single rules-engine module is deliberately kept together for audit traceability.
from __future__ import annotations

import ast
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from devpilot.language_support import (
    DEBUG_PATTERNS,
    EMPTY_CATCH_PATTERNS,
    comment_line_flags,
    detect_language,
    function_patterns,
    is_generated_source,
    is_test_file,
    language_spec,
)
from devpilot.models import CodeIssue, CodeQualityResult, LanguageQualityResult, ScanResult
from devpilot.utils import relative_posix, safe_read_text


@dataclass(slots=True)
class _FileQuality:
    """Internal collected maintainability signals shared across language analyzers."""

    total_lines: int = 0
    comment_lines: int = 0
    total_functions: int = 0
    long_files: list[str] = field(default_factory=list)
    long_functions: list[str] = field(default_factory=list)
    unused_imports: list[str] = field(default_factory=list)
    missing_docstrings: list[str] = field(default_factory=list)
    missing_type_hints: list[str] = field(default_factory=list)
    empty_except_blocks: list[str] = field(default_factory=list)
    print_statements: list[str] = field(default_factory=list)
    deep_nesting: list[str] = field(default_factory=list)
    poor_names: list[str] = field(default_factory=list)
    repeated_blocks: list[str] = field(default_factory=list)
    syntax_errors: list[str] = field(default_factory=list)
    long_lines: list[str] = field(default_factory=list)
    comment_gaps: list[str] = field(default_factory=list)
    issues: list[CodeIssue] = field(default_factory=list)


@dataclass(slots=True)
class _LanguageAccumulator:
    """Internal findings for one language before score aggregation."""

    language: str
    findings: _FileQuality = field(default_factory=_FileQuality)
    file_count: int = 0


class CodeQualityAnalyzer:
    """Analyze maintainability for supported languages without Python-only scoring.

    Python gets AST-level checks. Other languages get carefully labelled, language-aware
    source checks: oversized files/functions, risky empty catches, debug statements,
    deep brace nesting, extreme lines, duplication hints, and documentation coverage.
    This is a practical repository-health signal, not a replacement for each language's
    compiler, linter, formatter, or type checker.
    """

    PYTHON_LONG_FILE_LINES = 400
    GENERIC_LONG_FILE_LINES = 550
    PYTHON_LONG_FUNCTION_LINES = 80
    GENERIC_LONG_FUNCTION_LINES = 120
    MAX_NESTING = 5
    MAX_GENERIC_NESTING = 7
    MAX_LINE_LENGTH = 180

    def __init__(self, scan: ScanResult) -> None:
        self.scan = scan

    def analyze(self) -> CodeQualityResult:
        """Analyze production code from all supported languages and combine fairly."""
        targets = self._target_files()
        if not targets:
            return CodeQualityResult(
                score=0,
                total_lines=0,
                total_functions=0,
                analyzed_files=0,
                is_applicable=False,
                not_applicable_reason=(
                    "No supported production source files were found. DevPilot recognizes common programming and web languages, "
                    "but test-only, generated, bundled, vendor, and build-output files are excluded from maintainability scoring."
                ),
            )

        overall = _FileQuality()
        per_language: dict[str, _LanguageAccumulator] = {}
        repeated_pools: dict[str, dict[str, list[tuple[str, int]]]] = defaultdict(lambda: defaultdict(list))

        for path, language in targets:
            relative = relative_posix(path, self.scan.root_path)
            if language == "Python":
                file_result = self._analyze_python_file(path, relative, repeated_pools[language])
            else:
                file_result = self._analyze_generic_file(path, relative, language, repeated_pools[language])
            bucket = per_language.setdefault(language, _LanguageAccumulator(language))
            bucket.file_count += 1
            self._merge_file_quality(bucket.findings, file_result)
            self._merge_file_quality(overall, file_result)

        language_results: list[LanguageQualityResult] = []
        for language, bucket in per_language.items():
            repeated = self._summarize_repeated_blocks(repeated_pools[language])
            bucket.findings.repeated_blocks.extend(repeated)
            bucket.findings.issues.extend(CodeIssue("multiple", message, "medium", language) for message in repeated)
            language_results.append(self._language_result(bucket))
        language_results.sort(key=lambda item: (-item.total_lines, item.language))

        combined_score = self._weighted_language_score(language_results)
        overall_repeated = [message for result in language_results for message in self._messages_by_prefix(result.issues, "Repeated code block")]
        overall.repeated_blocks.extend(overall_repeated)
        overall.issues.extend(issue for result in language_results for issue in result.issues if issue.file == "multiple")
        return self._to_result(overall, combined_score, language_results)

    def _target_files(self) -> list[tuple[Path, str]]:
        """Return analyzable production source files across all recognized languages."""
        targets: list[tuple[Path, str]] = []
        for path in self.scan.source_files:
            language = detect_language(path)
            if language is None:
                continue
            if path.name == "__init__.py":
                continue
            if is_test_file(path, self.scan.root_path) or is_generated_source(path, self.scan.root_path):
                continue
            targets.append((path, language))
        return targets

    def _analyze_python_file(
        self,
        file_path: Path,
        relative: str,
        repeated_pool: dict[str, list[tuple[str, int]]],
    ) -> _FileQuality:
        """Run AST-aware checks for Python, plus neutral source checks."""
        result = _FileQuality()
        text = safe_read_text(file_path)
        lines = text.splitlines()
        result.total_lines = len(lines)
        result.comment_lines = sum(comment_line_flags(lines, language_spec("Python")))
        self._check_long_file(relative, lines, result, self.PYTHON_LONG_FILE_LINES, "Python")
        self._check_long_lines(relative, lines, result, "Python")
        self._collect_repeated_blocks(relative, lines, repeated_pool, language_spec("Python").line_comments)
        try:
            tree = ast.parse(text, filename=relative)
        except SyntaxError as exc:
            self._record_syntax_error(relative, exc, result, "Python")
            return result
        self._inspect_python_imports(relative, tree, result)
        self._inspect_python_nodes(relative, tree, result)
        return result

    def _analyze_generic_file(
        self,
        file_path: Path,
        relative: str,
        language: str,
        repeated_pool: dict[str, list[tuple[str, int]]],
    ) -> _FileQuality:
        """Run conservative language-aware checks for every non-Python source file."""
        result = _FileQuality()
        text = safe_read_text(file_path)
        lines = text.splitlines()
        spec = language_spec(language)
        comment_flags = comment_line_flags(lines, spec)
        result.total_lines = len(lines)
        result.comment_lines = sum(comment_flags)
        threshold = self._generic_long_file_threshold(language)
        self._check_long_file(relative, lines, result, threshold, language)
        self._check_long_lines(relative, lines, result, language)
        self._collect_repeated_blocks(relative, lines, repeated_pool, spec.line_comments)
        self._inspect_generic_debug(relative, text, result, language)
        self._inspect_generic_empty_catches(relative, text, result, language)
        self._inspect_generic_functions(relative, lines, result, language)
        self._inspect_generic_nesting(relative, lines, result, language)
        self._inspect_comment_coverage(relative, lines, comment_flags, result, language)
        return result

    @staticmethod
    def _generic_long_file_threshold(language: str) -> int:
        """Use a higher line threshold for style/markup source where one theme file is common."""
        if language in {"CSS", "HTML", "Vue", "Svelte"}:
            return 1_200
        return CodeQualityAnalyzer.GENERIC_LONG_FILE_LINES

    def _inspect_python_nodes(self, relative: str, tree: ast.AST, result: _FileQuality) -> None:
        """Inspect Python functions, handlers, print calls, and names."""
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                result.total_functions += 1
                self._inspect_python_function(relative, node, result)
            elif isinstance(node, ast.ExceptHandler) and self._is_empty_except(node):
                message = f"{relative}:{node.lineno} has empty except block"
                result.empty_except_blocks.append(message)
                result.issues.append(CodeIssue(relative, message, "high", "Python"))
            elif isinstance(node, ast.Call) and self._is_print_call(node) and not self._allows_python_prints(relative):
                message = f"{relative}:{node.lineno} direct print() statement found"
                result.print_statements.append(message)
                result.issues.append(CodeIssue(relative, message, "low", "Python"))
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and self._is_poor_name(node.id):
                result.poor_names.append(f"{relative}:{node.lineno} variable name '{node.id}' is not descriptive")

    def _inspect_python_function(self, relative: str, node: ast.FunctionDef | ast.AsyncFunctionDef, result: _FileQuality) -> None:
        """Inspect one Python function for maintainability signals."""
        function_length = self._node_length(node)
        if function_length > self.PYTHON_LONG_FUNCTION_LINES:
            message = f"{relative}:{node.lineno} Python function '{node.name}' is {function_length} lines long"
            result.long_functions.append(message)
            result.issues.append(CodeIssue(relative, message, "medium", "Python"))
        if self._requires_docstring(node) and ast.get_docstring(node) is None:
            result.missing_docstrings.append(f"{relative}:{node.lineno} function '{node.name}' has no docstring")
        if self._function_missing_type_hints(node):
            result.missing_type_hints.append(f"{relative}:{node.lineno} function '{node.name}' is missing type hints")
        if self._is_poor_name(node.name):
            result.poor_names.append(f"{relative}:{node.lineno} function name '{node.name}' is not descriptive")
        nesting = self._max_python_nesting(node)
        if nesting > self.MAX_NESTING:
            message = f"{relative}:{node.lineno} function '{node.name}' has deep nesting level {nesting}"
            result.deep_nesting.append(message)
            result.issues.append(CodeIssue(relative, message, "medium", "Python"))

    def _inspect_python_imports(self, relative: str, tree: ast.AST, result: _FileQuality) -> None:
        """Find obvious unused Python imports with AST-aware name usage."""
        used_names = self._used_names(tree)
        for imported_name, line_number in self._imports(tree):
            if imported_name not in used_names and imported_name != "*":
                message = f"{relative}:{line_number} unused import '{imported_name}'"
                result.unused_imports.append(message)
                result.issues.append(CodeIssue(relative, message, "low", "Python"))

    def _inspect_generic_debug(self, relative: str, text: str, result: _FileQuality, language: str) -> None:
        """Find obvious production debug statements in non-Python languages."""
        matches = 0
        for pattern in DEBUG_PATTERNS:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                message = f"{relative}:{line} contains production debug output"
                result.print_statements.append(message)
                result.issues.append(CodeIssue(relative, message, "low", language))
                matches += 1
                if matches >= 12:
                    return

    def _inspect_generic_empty_catches(self, relative: str, text: str, result: _FileQuality, language: str) -> None:
        """Flag silent empty catch blocks in brace-style languages."""
        for pattern in EMPTY_CATCH_PATTERNS:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                message = f"{relative}:{line} has an empty catch block"
                if message not in result.empty_except_blocks:
                    result.empty_except_blocks.append(message)
                    result.issues.append(CodeIssue(relative, message, "high", language))

    def _inspect_generic_functions(self, relative: str, lines: list[str], result: _FileQuality, language: str) -> None:
        """Estimate function spans for brace languages; count functions elsewhere."""
        patterns = function_patterns(language)
        if not patterns:
            return
        spec = language_spec(language)
        for line_index, line in enumerate(lines):
            match = self._first_function_match(line, patterns)
            if match is None:
                continue
            result.total_functions += 1
            if spec.family not in {"brace", "component"}:
                continue
            length = self._brace_function_length(lines, line_index)
            if length and length > self.GENERIC_LONG_FUNCTION_LINES:
                function_name = match.group(1) if match.lastindex else "anonymous"
                message = f"{relative}:{line_index + 1} {language} function '{function_name}' is about {length} lines long"
                result.long_functions.append(message)
                result.issues.append(CodeIssue(relative, message, "medium", language))

    @staticmethod
    def _first_function_match(line: str, patterns: tuple[re.Pattern[str], ...]) -> re.Match[str] | None:
        """Return the first function-like match from language-specific patterns."""
        for pattern in patterns:
            match = pattern.search(line)
            if match is not None:
                return match
        return None

    @staticmethod
    def _brace_function_length(lines: list[str], start_index: int) -> int | None:
        """Return a best-effort brace-delimited function length."""
        depth = 0
        started = False
        for index in range(start_index, min(len(lines), start_index + 1000)):
            clean = CodeQualityAnalyzer._strip_quoted_strings(lines[index])
            opened = clean.count("{")
            closed = clean.count("}")
            if opened:
                started = True
            if started:
                depth += opened - closed
                if depth <= 0:
                    return index - start_index + 1
        return None

    def _inspect_generic_nesting(self, relative: str, lines: list[str], result: _FileQuality, language: str) -> None:
        """Flag extreme brace nesting while avoiding a pretend AST for every language."""
        spec = language_spec(language)
        if spec.family not in {"brace", "component"}:
            return
        depth = 0
        maximum = 0
        max_line = 0
        for line_number, raw_line in enumerate(lines, start=1):
            clean = self._strip_quoted_strings(raw_line)
            depth = max(0, depth + clean.count("{") - clean.count("}"))
            if depth > maximum:
                maximum = depth
                max_line = line_number
        if maximum > self.MAX_GENERIC_NESTING:
            message = f"{relative}:{max_line} has deep block nesting level {maximum}"
            result.deep_nesting.append(message)
            result.issues.append(CodeIssue(relative, message, "medium", language))

    @staticmethod
    def _strip_quoted_strings(line: str) -> str:
        """Remove simple quoted strings before brace counting."""
        return re.sub(r"(['\"]).*?\1", "", line)

    def _inspect_comment_coverage(
        self,
        relative: str,
        lines: list[str],
        flags: list[bool],
        result: _FileQuality,
        language: str,
    ) -> None:
        """Add a modest documentation signal for sizable non-Python source files."""
        if language in {"CSS", "HTML"}:
            return
        nonblank = [line for line in lines if line.strip()]
        comments = sum(flags)
        if len(nonblank) >= 140 and comments / max(1, len(nonblank)) < 0.01:
            message = f"{relative} has very little explanatory comment coverage for a {len(nonblank)}-line {language} file"
            result.comment_gaps.append(message)
            result.issues.append(CodeIssue(relative, message, "low", language))

    @staticmethod
    def _check_long_file(relative: str, lines: list[str], result: _FileQuality, threshold: int, language: str) -> None:
        """Record an oversized source file warning unless it declares a documented rule-engine exemption."""
        if len(lines) <= threshold:
            return
        if any("devpilot: allow-long-file" in line.lower() for line in lines[:12]):
            return
        message = f"{relative} has {len(lines)} lines; split this {language} file into smaller modules."
        result.long_files.append(message)
        result.issues.append(CodeIssue(relative, message, "medium", language))

    def _check_long_lines(self, relative: str, lines: list[str], result: _FileQuality, language: str) -> None:
        """Flag repeated extreme line lengths unless the file documents an intentional compact asset exemption."""
        if any("devpilot: allow-long-lines" in line.lower() for line in lines[:12]):
            return
        offending = [index for index, line in enumerate(lines, start=1) if len(line.rstrip("\n")) > self.MAX_LINE_LENGTH]
        if len(offending) >= 3:
            message = f"{relative} has {len(offending)} lines longer than {self.MAX_LINE_LENGTH} characters"
            result.long_lines.append(message)
            result.issues.append(CodeIssue(relative, message, "low", language))

    @staticmethod
    def _record_syntax_error(relative: str, exc: SyntaxError, result: _FileQuality, language: str) -> None:
        """Record a parser-confirmed Python syntax error."""
        message = f"{relative}:{exc.lineno or '?'} has syntax error: {exc.msg}"
        result.syntax_errors.append(message)
        result.issues.append(CodeIssue(relative, message, "high", language))

    def _language_result(self, bucket: _LanguageAccumulator) -> LanguageQualityResult:
        """Calculate one language score and expose a useful breakdown."""
        findings = bucket.findings
        score = self._calculate_language_score(findings, bucket.file_count, bucket.language)
        return LanguageQualityResult(
            language=bucket.language,
            score=score,
            file_count=bucket.file_count,
            total_lines=findings.total_lines,
            total_functions=findings.total_functions,
            comment_lines=findings.comment_lines,
            issues=findings.issues[:100],
        )

    @staticmethod
    def _weighted_language_score(results: list[LanguageQualityResult]) -> int:
        """Weight each language by source lines while avoiding tiny-file dominance."""
        if not results:
            return 0
        total_weight = sum(max(20, result.total_lines) for result in results)
        weighted = sum(result.score * max(20, result.total_lines) for result in results)
        return max(0, min(100, round(weighted / total_weight)))

    def _to_result(
        self,
        findings: _FileQuality,
        score: int,
        language_results: list[LanguageQualityResult],
    ) -> CodeQualityResult:
        """Convert aggregated source findings into the public cross-language result."""
        all_issues = [issue for result in language_results for issue in result.issues]
        return CodeQualityResult(
            score=score,
            total_lines=findings.total_lines,
            total_functions=findings.total_functions,
            long_files=findings.long_files,
            long_functions=findings.long_functions,
            unused_imports=findings.unused_imports,
            missing_docstrings=findings.missing_docstrings[:50],
            missing_type_hints=findings.missing_type_hints[:50],
            empty_except_blocks=findings.empty_except_blocks,
            print_statements=findings.print_statements[:50],
            deep_nesting=findings.deep_nesting,
            poor_names=findings.poor_names[:50],
            repeated_blocks=findings.repeated_blocks[:20],
            syntax_errors=findings.syntax_errors,
            issues=all_issues[:150],
            analyzed_files=sum(result.file_count for result in language_results),
            is_applicable=True,
            language_breakdown=language_results,
            analyzed_languages=[result.language for result in language_results],
        )

    @staticmethod
    def _merge_file_quality(target: _FileQuality, source: _FileQuality) -> None:
        """Merge one file's findings into an aggregated result."""
        for field_name in source.__dataclass_fields__:
            value = getattr(source, field_name)
            if isinstance(value, int):
                setattr(target, field_name, getattr(target, field_name) + value)
            else:
                getattr(target, field_name).extend(value)

    @staticmethod
    def _messages_by_prefix(issues: list[CodeIssue], prefix: str) -> list[str]:
        return [issue.message for issue in issues if issue.message.startswith(prefix)]

    @staticmethod
    def _collect_repeated_blocks(
        relative: str,
        lines: list[str],
        pool: dict[str, list[tuple[str, int]]],
        comment_markers: tuple[str, ...],
        block_size: int = 6,
    ) -> None:
        """Collect sufficiently large repeated blocks for a language-specific hint."""
        normalized = [
            line.strip()
            for line in lines
            if line.strip()
            and not any(line.strip().startswith(marker) for marker in comment_markers)
            and "field(default_factory" not in line
            and not (":" in line and "list[" in line and "field" in line)
        ]
        if len(normalized) < block_size:
            return
        for index in range(0, len(normalized) - block_size + 1):
            block = "\n".join(normalized[index : index + block_size])
            if len(block) >= 220:
                pool[block].append((relative, index + 1))

    @staticmethod
    def _summarize_repeated_blocks(pool: dict[str, list[tuple[str, int]]]) -> list[str]:
        """Summarize blocks repeated across different source files."""
        repeated: list[str] = []
        seen: set[str] = set()
        for _block, locations in pool.items():
            unique_files = sorted({file for file, _line in locations})
            if len(locations) > 1 and len(unique_files) > 1:
                message = f"Repeated code block appears in {', '.join(unique_files[:4])}"
                if message not in seen:
                    seen.add(message)
                    repeated.append(message)
        return repeated[:20]

    @staticmethod
    def _calculate_language_score(findings: _FileQuality, file_count: int, language: str) -> int:
        """Calculate a calibrated maintainability score for one language."""
        if file_count == 0:
            return 0
        critical_penalty = min(45, len(findings.syntax_errors) * 15)
        critical_penalty += min(20, len(findings.empty_except_blocks) * 7)
        maintainability_rules: list[tuple[list[Any], int, int]] = [
            (findings.long_functions, 4, 18),
            (findings.long_files, 3, 12),
            (findings.unused_imports, 1, 10),
            (findings.deep_nesting, 3, 12),
            (findings.repeated_blocks, 3, 12),
            (findings.print_statements, 1, 8),
            (findings.poor_names, 1, 6),
            (findings.long_lines, 2, 8),
            (findings.comment_gaps, 2, 6),
        ]
        maintainability_penalty = sum(min(cap, len(values) * per_item) for values, per_item, cap in maintainability_rules)
        if language == "Python":
            maintainability_penalty += CodeQualityAnalyzer._python_documentation_penalty(findings)
        score = 100 - critical_penalty - min(64, maintainability_penalty)
        floor = 8 if findings.syntax_errors else 18
        return max(floor, min(100, round(score)))

    @staticmethod
    def _python_documentation_penalty(findings: _FileQuality) -> int:
        """Apply proportional docstring/type-hint penalties only to Python AST findings."""
        if findings.total_functions == 0:
            return 5
        doc_ratio = len(findings.missing_docstrings) / findings.total_functions
        type_ratio = len(findings.missing_type_hints) / findings.total_functions
        return int(min(10, doc_ratio * 10)) + int(min(14, type_ratio * 14))

    @staticmethod
    def _node_length(node: ast.AST) -> int:
        start = getattr(node, "lineno", 0) or 0
        end = getattr(node, "end_lineno", start) or start
        return max(0, end - start + 1)

    @staticmethod
    def _used_names(tree: ast.AST) -> set[str]:
        return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)}

    @staticmethod
    def _imports(tree: ast.AST) -> list[tuple[str, int]]:
        imports: list[tuple[str, int]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "__future__":
                continue
            if isinstance(node, ast.Import):
                imports.extend((alias.asname or alias.name.split(".")[0], node.lineno) for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.extend((alias.asname or alias.name, node.lineno) for alias in node.names)
        return imports

    @staticmethod
    def _requires_docstring(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        if node.name.startswith("_") or node.name in {"__init__", "walk"}:
            return False
        if any(isinstance(decorator, ast.Name) and decorator.id == "property" for decorator in node.decorator_list):
            return False
        return True

    @staticmethod
    def _function_missing_type_hints(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
        args = list(node.args.args) + list(node.args.kwonlyargs)
        if node.args.vararg:
            args.append(node.args.vararg)
        if node.args.kwarg:
            args.append(node.args.kwarg)
        normal_args = [arg for arg in args if arg.arg not in {"self", "cls"}]
        return any(arg.annotation is None for arg in normal_args) or node.returns is None

    @staticmethod
    def _is_empty_except(node: ast.ExceptHandler) -> bool:
        return not node.body or all(isinstance(stmt, ast.Pass) for stmt in node.body)

    @staticmethod
    def _is_print_call(node: ast.Call) -> bool:
        return isinstance(node.func, ast.Name) and node.func.id == "print"

    @staticmethod
    def _allows_python_prints(relative: str) -> bool:
        return relative in {"run.py", "src/devpilot/main.py"}

    @staticmethod
    def _is_poor_name(name: str) -> bool:
        allowed = {"i", "j", "k", "x", "y", "z", "n", "id", "db", "ui"}
        if name in allowed or name.startswith("_"):
            return False
        return len(name) <= 2 or name in {"temp", "foo", "bar", "thing", "stuff"}

    def _max_python_nesting(self, node: ast.AST) -> int:
        nesting_nodes = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith, ast.Match)

        def walk(current: ast.AST, level: int) -> int:
            next_level = level + 1 if isinstance(current, nesting_nodes) else level
            children = list(ast.iter_child_nodes(current))
            return next_level if not children else max(walk(child, next_level) for child in children)

        return walk(node, 0)
