"""Language detection and lightweight cross-language quality heuristics.

DevPilot intentionally separates *language detection* from *deep parsing*.
Python receives AST-aware checks from the standard library, while every supported
source language receives neutral, text-based maintainability checks. This keeps
results useful for mixed repositories without claiming compiler-level certainty.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True, slots=True)
class LanguageSpec:
    """Metadata used by the scanner and generic code-quality analyzer."""

    name: str
    extensions: tuple[str, ...]
    line_comments: tuple[str, ...]
    block_comment_pairs: tuple[tuple[str, str], ...] = ()
    family: str = "generic"


LANGUAGES: tuple[LanguageSpec, ...] = (
    LanguageSpec("Python", (".py", ".pyi"), ("#",), family="python"),
    LanguageSpec("JavaScript", (".js", ".mjs", ".cjs", ".jsx"), ("//",), (("/*", "*/"),), "brace"),
    LanguageSpec("TypeScript", (".ts", ".tsx", ".mts", ".cts"), ("//",), (("/*", "*/"),), "brace"),
    LanguageSpec("Java", (".java",), ("//",), (("/*", "*/"),), "brace"),
    LanguageSpec("C#", (".cs",), ("//",), (("/*", "*/"),), "brace"),
    LanguageSpec("C++", (".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx"), ("//",), (("/*", "*/"),), "brace"),
    LanguageSpec("C", (".c", ".h"), ("//",), (("/*", "*/"),), "brace"),
    LanguageSpec("Go", (".go",), ("//",), (("/*", "*/"),), "brace"),
    LanguageSpec("Rust", (".rs",), ("//",), (("/*", "*/"),), "brace"),
    LanguageSpec("PHP", (".php",), ("//", "#"), (("/*", "*/"),), "brace"),
    LanguageSpec("Ruby", (".rb",), ("#",), family="ruby"),
    LanguageSpec("Kotlin", (".kt", ".kts"), ("//",), (("/*", "*/"),), "brace"),
    LanguageSpec("Swift", (".swift",), ("//",), (("/*", "*/"),), "brace"),
    LanguageSpec("Dart", (".dart",), ("//",), (("/*", "*/"),), "brace"),
    LanguageSpec("Scala", (".scala", ".sc"), ("//",), (("/*", "*/"),), "brace"),
    LanguageSpec("R", (".r", ".R"), ("#",), family="r"),
    LanguageSpec("Lua", (".lua",), ("--",), (("--[[", "]]"),), "lua"),
    LanguageSpec("Shell", (".sh", ".bash", ".zsh", ".fish"), ("#",), family="shell"),
    LanguageSpec("PowerShell", (".ps1", ".psm1", ".psd1"), ("#",), (("<#", "#>"),), "powershell"),
    LanguageSpec("SQL", (".sql",), ("--",), (("/*", "*/"),), "sql"),
    LanguageSpec("HTML", (".html", ".htm"), (), (("<!--", "-->"),), "markup"),
    LanguageSpec("CSS", (".css", ".scss", ".sass", ".less"), ("//",), (("/*", "*/"),), "style"),
    LanguageSpec("Vue", (".vue",), ("//",), (("<!--", "-->"), ("/*", "*/")), "component"),
    LanguageSpec("Svelte", (".svelte",), ("//",), (("<!--", "-->"), ("/*", "*/")), "component"),
    LanguageSpec("Elixir", (".ex", ".exs"), ("#",), family="elixir"),
    LanguageSpec("Clojure", (".clj", ".cljs", ".cljc"), (";",), family="lisp"),
    LanguageSpec("Haskell", (".hs",), ("--",), (("{-", "-}"),), "haskell"),
    LanguageSpec("Perl", (".pl", ".pm"), ("#",), family="perl"),
    LanguageSpec("Zig", (".zig",), ("//",), family="brace"),
    LanguageSpec("F#", (".fs", ".fsx"), ("//",), (("(*", "*)"),), "fsharp"),
    LanguageSpec("MATLAB", (".m",), ("%",), family="matlab"),
    LanguageSpec("Terraform", (".tf",), ("#", "//"), (("/*", "*/"),), "hcl"),
)

_EXTENSION_MAP: dict[str, LanguageSpec] = {
    extension.lower(): spec
    for spec in LANGUAGES
    for extension in spec.extensions
}

# Exclude common machine-generated/minified/vendor sources from maintainability.
GENERATED_NAME_MARKERS = (
    ".min.",
    ".bundle.",
    ".generated.",
    ".gen.",
    "_generated.",
    "_pb2.",
    "_pb.",
    ".designer.",
    ".g.",
)
GENERATED_DIR_MARKERS = {
    "node_modules",
    "vendor",
    "dist",
    "build",
    "target",
    ".next",
    ".nuxt",
    ".angular",
    "coverage",
    "generated",
    "gen",
    "third_party",
    "packages",
}


FUNCTION_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "brace": (
        re.compile(r"\b(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\("),
        re.compile(r"\b(?:public|private|protected|internal|static|async|virtual|override|final|synchronized|inline|extern|unsafe|const|mutating|nonmutating|operator|friend|sealed|abstract|partial|open|suspend|override\s+)*\s*(?:[A-Za-z_][\w:<>,.?\[\]\s*&]+)\s+([A-Za-z_$][\w$]*)\s*\([^;{}]*\)\s*(?:throws\s+[\w.]+)?\s*\{"),
        re.compile(r"\b([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>\s*\{"),
        re.compile(r"\bfunc\s+([A-Za-z_][\w]*)\s*\("),
        re.compile(r"\bfn\s+([A-Za-z_][\w]*)\s*\("),
    ),
    "ruby": (re.compile(r"^\s*def\s+([A-Za-z_][\w!?=]*)", re.MULTILINE),),
    "shell": (re.compile(r"^\s*(?:function\s+)?([A-Za-z_][\w-]*)\s*\(\s*\)\s*\{", re.MULTILINE),),
    "powershell": (re.compile(r"^\s*function\s+([A-Za-z_][\w-]*)", re.IGNORECASE | re.MULTILINE),),
    "lua": (re.compile(r"^\s*(?:local\s+)?function\s+([A-Za-z_][\w.]*)", re.MULTILINE),),
    "elixir": (re.compile(r"^\s*defp?\s+([A-Za-z_][\w!?]*)", re.MULTILINE),),
    "haskell": (re.compile(r"^\s*([a-z][\w']*)\s*(?:::\s*|[^=]*=)", re.MULTILINE),),
    "fsharp": (re.compile(r"^\s*let\s+(?:rec\s+)?([A-Za-z_][\w']*)", re.MULTILINE),),
    "matlab": (re.compile(r"^\s*function\s+(?:\[[^\]]+\]\s*=\s*)?([A-Za-z_][\w]*)", re.MULTILINE),),
    "r": (re.compile(r"^\s*([A-Za-z.][\w.]*)\s*(?:<-|=)\s*function\s*\(", re.MULTILINE),),
    "perl": (re.compile(r"^\s*sub\s+([A-Za-z_][\w]*)", re.MULTILINE),),
    "sql": (),
    "markup": (),
    "style": (),
    "component": (
        re.compile(r"\b(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\("),
        re.compile(r"\b([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>\s*\{"),
    ),
    "lisp": (re.compile(r"\(defn[-]?\s+([\w*+!?.-]+)"),),
    "hcl": (),
}

DEBUG_PATTERNS = (
    re.compile(r"\bconsole\.(?:log|debug|trace)\s*\("),
    re.compile(r"\bSystem\.out\.(?:print|println|printf)\s*\("),
    re.compile(r"\bfmt\.(?:Print|Printf|Println)\s*\("),
    re.compile(r"\bprintln!\s*\("),
    re.compile(r"\b(?:var_dump|print_r|dd)\s*\("),
    re.compile(r"\bdebugger\s*;?"),
)

EMPTY_CATCH_PATTERNS = (
    re.compile(r"\bcatch\s*(?:\([^)]*\))?\s*\{\s*\}", re.DOTALL),
    re.compile(r"\bcatch\s*(?:\([^)]*\))?\s*\{\s*(?://[^\n]*)?\s*\}", re.DOTALL),
)


def detect_language(path: Path) -> str | None:
    """Return a normalized language name from a source-file extension."""
    spec = _EXTENSION_MAP.get(path.suffix.lower())
    return spec.name if spec else None


def language_spec(language: str) -> LanguageSpec:
    """Return the support metadata for an already detected language."""
    for spec in LANGUAGES:
        if spec.name == language:
            return spec
    raise KeyError(f"Unsupported language metadata requested: {language}")


def is_source_file(path: Path) -> bool:
    """Return whether a file has a supported code or web-source extension."""
    return detect_language(path) is not None


def is_generated_source(path: Path, root: Path | None = None) -> bool:
    """Return whether a source file is likely generated, bundled, or vendor content."""
    lower_name = path.name.lower()
    if any(marker in lower_name for marker in GENERATED_NAME_MARKERS):
        return True
    parts = path.parts
    if root is not None:
        try:
            parts = path.relative_to(root).parts
        except ValueError:
            parts = path.parts
    return any(part.lower() in GENERATED_DIR_MARKERS for part in parts[:-1])


def is_test_file(path: Path, root: Path | None = None) -> bool:
    """Recognize common cross-language test naming conventions."""
    name = path.name.lower()
    parts = path.parts
    if root is not None:
        try:
            parts = path.relative_to(root).parts
        except ValueError:
            parts = path.parts
    if any(part.lower() in {"test", "tests", "__tests__", "spec", "specs"} for part in parts[:-1]):
        return True
    test_markers = (
        "test_",
        "_test.",
        ".test.",
        ".spec.",
        "tests.",
        "test.java",
        "test.kt",
        "test.cs",
    )
    return name.startswith("test") or any(marker in name for marker in test_markers)


def comment_line_flags(lines: list[str], spec: LanguageSpec) -> list[bool]:
    """Mark lines that are comments using conservative language-aware delimiters."""
    flags = [False] * len(lines)
    active_end: str | None = None
    for index, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        if active_end:
            flags[index] = True
            if active_end in stripped:
                active_end = None
            continue
        if not stripped:
            continue
        if any(stripped.startswith(marker) for marker in spec.line_comments):
            flags[index] = True
            continue
        for start, end in spec.block_comment_pairs:
            if stripped.startswith(start):
                flags[index] = True
                if end not in stripped[len(start) :]:
                    active_end = end
                break
    return flags


def function_patterns(language: str) -> tuple[re.Pattern[str], ...]:
    """Return lightweight best-effort function detectors for one language family."""
    spec = language_spec(language)
    return FUNCTION_PATTERNS.get(spec.family, ())


def major_languages(language_files: dict[str, list[Path]], limit: int = 5) -> list[tuple[str, int]]:
    """Return language counts ordered for dashboard and CLI display."""
    return sorted(((name, len(paths)) for name, paths in language_files.items()), key=lambda item: (-item[1], item[0]))[:limit]
