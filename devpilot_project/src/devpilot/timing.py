"""Workload estimation helpers for DevPilot repository audits."""

from __future__ import annotations

import math
from pathlib import Path

from devpilot.language_support import is_generated_source, is_test_file
from devpilot.models import ScanResult, WorkloadEstimate


def estimate_from_scan(scan: ScanResult) -> WorkloadEstimate:
    """Estimate audit duration from repository size and all analyzable source files."""
    total_size = sum(_file_size(path) for path in scan.all_files)
    analyzable_python = sum(
        1
        for path in scan.python_files
        if not is_test_file(path, scan.root_path) and not is_generated_source(path, scan.root_path)
    )
    analyzable_source = sum(
        1
        for path in scan.source_files
        if not is_test_file(path, scan.root_path) and not is_generated_source(path, scan.root_path)
    )
    megabytes = total_size / (1024 * 1024)

    # UX estimate only: cross-language text analysis is cheaper than compiler/linter runs,
    # but larger mixed repositories still deserve a visible countdown.
    seconds = 3.0 + (scan.total_files * 0.018) + (analyzable_source * 0.31) + (analyzable_python * 0.10) + (megabytes * 0.24)
    estimated = max(4, min(900, math.ceil(seconds)))
    spread = max(3, math.ceil(estimated * 0.30))
    confidence = "high" if scan.total_files < 400 else "medium"

    return WorkloadEstimate(
        estimated_seconds=estimated,
        lower_seconds=max(3, estimated - spread),
        upper_seconds=min(1200, estimated + spread),
        total_files=scan.total_files,
        python_files=scan.python_file_count,
        analyzable_python_files=analyzable_python,
        total_size_bytes=total_size,
        confidence=confidence,
        source_files=scan.source_file_count,
        analyzable_source_files=analyzable_source,
    )


def remote_placeholder_estimate() -> WorkloadEstimate:
    """Return a transparent initial estimate before a GitHub repository is cloned."""
    return WorkloadEstimate(
        estimated_seconds=45,
        lower_seconds=25,
        upper_seconds=90,
        total_files=0,
        python_files=0,
        analyzable_python_files=0,
        total_size_bytes=0,
        confidence="initial",
        is_remote_placeholder=True,
        source_files=0,
        analyzable_source_files=0,
    )


def format_duration(seconds: float | int) -> str:
    """Format a duration for a human-facing dashboard label."""
    rounded = max(0, int(round(seconds)))
    if rounded < 60:
        return f"{rounded} sec"
    minutes, remainder = divmod(rounded, 60)
    if remainder < 15:
        return f"{minutes} min"
    return f"{minutes} min {remainder} sec"


def estimate_message(estimate: WorkloadEstimate) -> str:
    """Return a compact explanation for dashboard ETA cards."""
    if estimate.is_remote_placeholder:
        return "GitHub repository size is measured after the secure shallow clone."
    language_text = f"{estimate.analyzable_source_files} production source file(s)"
    return (
        f"Estimated range {format_duration(estimate.lower_seconds)}–{format_duration(estimate.upper_seconds)} "
        f"from {estimate.total_files} files and {language_text}."
    )


def _file_size(path: Path) -> int:
    """Return file size safely when filesystem entries disappear during a scan."""
    try:
        return path.stat().st_size
    except OSError:
        return 0
