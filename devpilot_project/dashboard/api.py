"""FastAPI application for the DevPilot web dashboard.

The dashboard uses the supplied HTML/CSS/JavaScript experience while this API
runs the multi-language DevPilot engine from ``src/devpilot``.  Analysis runs in
background jobs so the browser receives real stage, percentage, and ETA updates
instead of a fake loading animation.
"""

from __future__ import annotations

import json
import sys
import threading
import time
import uuid
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for import_path in (SRC, ROOT):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

from devpilot.main import analyze_repository, prepare_analysis  # noqa: E402
from devpilot.models import AnalysisProgress, RepositoryReport, WorkloadEstimate  # noqa: E402
from devpilot.report_generator import ReportGenerator  # noqa: E402
from dashboard.serializers import report_to_dashboard_payload  # noqa: E402


app = FastAPI(
    title="DevPilot Repository Intelligence API",
    description="Background analysis API for the DevPilot dashboard.",
    version="2.0.0",
)
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


class AnalyzeRequest(BaseModel):
    """Accepted analysis sources, including backward-compatible fields."""

    source: str | None = Field(default=None, max_length=2048)
    repo_url: str | None = Field(default=None, max_length=2048)
    local_path: str | None = Field(default=None, max_length=4096)
    analysis_type: Literal["github", "local", "auto"] = "auto"


@dataclass(slots=True)
class AuditJob:
    """One in-memory audit job with only process-local state."""

    job_id: str
    source: str
    state: str = "queued"
    phase: str = "queued"
    label: str = "Queued for analysis"
    percent: int = 0
    created_at: float = field(default_factory=time.perf_counter)
    started_at: float | None = None
    finished_at: float | None = None
    estimate: WorkloadEstimate | None = None
    report: RepositoryReport | None = None
    error: str | None = None
    events: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=20))


JOBS: dict[str, AuditJob] = {}
JOBS_LOCK = threading.RLock()
EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="devpilot-web-audit")
MAX_JOBS = 30


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    """Serve the provided UI template unchanged as the dashboard shell."""
    return (ROOT / "templates" / "index.html").read_text(encoding="utf-8")


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    """Avoid noisy browser 404 logs when no custom favicon is bundled."""
    return Response(status_code=204)


@app.get("/api/health")
def health_check() -> dict[str, str]:
    """Return a small health payload suitable for startup checks."""
    return {"status": "healthy", "engine": "DevPilot multi-language analyzer", "version": "2.0.0"}


@app.post("/api/analyze", status_code=202)
def create_analysis(request: AnalyzeRequest) -> dict[str, Any]:
    """Create an asynchronous repository analysis job."""
    source = _resolve_source(request)
    job = AuditJob(job_id=uuid.uuid4().hex, source=source)
    job.events.append(_event_payload("queued", job.label, 0))
    with JOBS_LOCK:
        _prune_jobs()
        JOBS[job.job_id] = job
    EXECUTOR.submit(_run_job, job.job_id)
    return {"jobId": job.job_id, "state": job.state, "source": source}


@app.get("/api/jobs/{job_id}")
def get_analysis_job(job_id: str) -> dict[str, Any]:
    """Return real-time progress and the completed dashboard report, if ready."""
    job = _get_job(job_id)
    return _job_snapshot(job, include_report=True)


@app.get("/api/jobs/{job_id}/export/{format_name}")
def export_job_report(job_id: str, format_name: Literal["json", "markdown", "html"]) -> Response:
    """Download a real export generated from the same completed analysis report."""
    job = _get_job(job_id)
    if job.state != "completed" or job.report is None:
        raise HTTPException(status_code=409, detail="The report is not ready to export yet.")
    safe_name = _safe_filename(job.report.repository_name)
    if format_name == "json":
        content = json.dumps(job.report.as_dict(), indent=2, default=str)
        return _download_response(content, "application/json", f"devpilot_{safe_name}.json")
    if format_name == "markdown":
        content = ReportGenerator.to_markdown(job.report)
        return _download_response(content, "text/markdown; charset=utf-8", f"devpilot_{safe_name}.md")
    content = ReportGenerator.to_html(job.report)
    return _download_response(content, "text/html; charset=utf-8", f"devpilot_{safe_name}.html")


@app.get("/api/history")
def analysis_history() -> dict[str, list[dict[str, Any]]]:
    """Return the latest completed in-memory analyses for the history affordance."""
    with JOBS_LOCK:
        complete = [job for job in JOBS.values() if job.state == "completed" and job.report is not None]
        entries = sorted(complete, key=lambda item: item.finished_at or 0.0, reverse=True)[:8]
        return {
            "items": [
                {
                    "jobId": job.job_id,
                    "repository": job.report.repository_name,
                    "score": job.report.score.overall_score,
                    "grade": job.report.score.grade,
                    "source": job.source,
                    "completedSecondsAgo": round(max(0.0, time.perf_counter() - (job.finished_at or time.perf_counter())), 1),
                }
                for job in entries
            ]
        }


@app.get("/api/jobs/{job_id}/raw")
def raw_job_report(job_id: str) -> Response:
    """Expose the machine-readable raw report for integrations and debugging."""
    job = _get_job(job_id)
    if job.state != "completed" or job.report is None:
        raise HTTPException(status_code=409, detail="The report is not ready yet.")
    return Response(
        content=json.dumps(job.report.as_dict(), indent=2, default=str),
        media_type="application/json",
    )


def _resolve_source(request: AnalyzeRequest) -> str:
    """Read the new API field or legacy UI fields without ambiguous empty values."""
    source = (request.source or request.repo_url or request.local_path or "").strip()
    if not source:
        raise HTTPException(status_code=400, detail="Enter a local repository path or public GitHub repository URL.")
    return source


def _run_job(job_id: str) -> None:
    """Execute a repository audit and write all worker updates under a lock."""
    job = _get_job(job_id)
    try:
        _update_job(job, state="preparing", phase="calibrate", label="Calibrating repository workload", percent=2)
        preflight = prepare_analysis(job.source)
        _update_estimate(job, preflight.estimate)
        _update_job(
            job,
            phase="calibrate",
            label=_calibration_label(preflight.estimate),
            percent=8 if preflight.is_remote else 20,
        )

        def on_progress(event: AnalysisProgress) -> None:
            _apply_progress(job, event)

        report = analyze_repository(
            job.source,
            pre_scanned=preflight.scan,
            estimated_seconds=preflight.estimate.estimated_seconds,
            progress_callback=on_progress,
        )
        _update_job(
            job,
            state="completed",
            phase="complete",
            label="Repository intelligence is ready",
            percent=100,
            report=report,
        )
    except Exception as exc:  # pragma: no cover - defensive API boundary
        _update_job(job, state="failed", phase="failed", label="Analysis failed", error=str(exc))


def _apply_progress(job: AuditJob, event: AnalysisProgress) -> None:
    """Record progress emitted by the production analyzer."""
    if event.estimate_seconds is not None and job.estimate is not None:
        _update_estimate(job, _recalibrated_estimate(job.estimate, event.estimate_seconds))
    _update_job(job, phase=event.phase, label=event.label, percent=event.percent)


def _recalibrated_estimate(previous: WorkloadEstimate, seconds: int) -> WorkloadEstimate:
    """Adjust an initial remote range after the real repository has been inspected."""
    spread = max(3, round(seconds * 0.30))
    return replace(
        previous,
        estimated_seconds=seconds,
        lower_seconds=max(2, seconds - spread),
        upper_seconds=seconds + spread,
        confidence="calibrated",
        is_remote_placeholder=False,
    )


def _update_estimate(job: AuditJob, estimate: WorkloadEstimate) -> None:
    """Store an updated workload estimate safely."""
    with JOBS_LOCK:
        job.estimate = estimate


def _update_job(
    job: AuditJob,
    *,
    state: str | None = None,
    phase: str | None = None,
    label: str | None = None,
    percent: int | None = None,
    report: RepositoryReport | None = None,
    error: str | None = None,
) -> None:
    """Atomically update a job and append a small meaningful event timeline."""
    with JOBS_LOCK:
        if state is not None:
            job.state = state
            if state == "preparing" and job.started_at is None:
                job.started_at = time.perf_counter()
            if state in {"completed", "failed"}:
                job.finished_at = time.perf_counter()
        if phase is not None:
            job.phase = phase
        if label is not None:
            job.label = label
        if percent is not None:
            job.percent = max(0, min(100, int(percent)))
        if report is not None:
            job.report = report
        if error is not None:
            job.error = error
        current = _event_payload(job.phase, job.label, job.percent)
        if not job.events or job.events[-1] != current:
            job.events.append(current)


def _job_snapshot(job: AuditJob, *, include_report: bool) -> dict[str, Any]:
    """Return only browser-safe, JSON-serializable state for one audit job."""
    with JOBS_LOCK:
        now = time.perf_counter()
        started = job.started_at or job.created_at
        elapsed = max(0.0, (job.finished_at or now) - started)
        estimate = job.estimate
        timing = {
            "elapsedSeconds": round(elapsed, 1),
            "estimatedSeconds": estimate.estimated_seconds if estimate else None,
            "lowerSeconds": estimate.lower_seconds if estimate else None,
            "upperSeconds": estimate.upper_seconds if estimate else None,
            "confidence": estimate.confidence if estimate else "calibrating",
            "longRunning": estimate.is_long_running if estimate else False,
            "totalFiles": estimate.total_files if estimate else None,
            "sourceFiles": estimate.source_files if estimate else None,
        }
        snapshot: dict[str, Any] = {
            "jobId": job.job_id,
            "source": job.source,
            "state": job.state,
            "progress": {"phase": job.phase, "label": job.label, "percent": job.percent},
            "timing": timing,
            "events": list(job.events),
            "error": job.error,
        }
        if include_report and job.report is not None:
            snapshot["report"] = report_to_dashboard_payload(job.report)
        return snapshot


def _get_job(job_id: str) -> AuditJob:
    """Look up a live job or return a proper API error."""
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Analysis job was not found. Start a new audit.")
    return job


def _prune_jobs() -> None:
    """Keep in-memory history bounded while retaining the newest useful reports."""
    if len(JOBS) < MAX_JOBS:
        return
    ordered = sorted(JOBS.values(), key=lambda item: item.finished_at or item.created_at)
    for stale in ordered[: max(1, len(ordered) - MAX_JOBS + 1)]:
        JOBS.pop(stale.job_id, None)


def _event_payload(phase: str, label: str, percent: int) -> dict[str, Any]:
    return {"phase": phase, "label": label, "percent": max(0, min(100, int(percent)))}


def _calibration_label(estimate: WorkloadEstimate) -> str:
    """Explain the first estimate in a human-readable way."""
    if estimate.is_remote_placeholder:
        return f"Remote audit estimate: approximately {estimate.lower_seconds}–{estimate.upper_seconds} seconds"
    return f"Workload calibrated: approximately {estimate.estimated_seconds} seconds"


def _safe_filename(value: str) -> str:
    """Return a compact filesystem-safe report name."""
    cleaned = "".join(character if character.isalnum() or character in {"-", "_"} else "-" for character in value)
    return cleaned.strip("-")[:80] or "repository"


def _download_response(content: str, media_type: str, filename: str) -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


if __name__ == "__main__":  # pragma: no cover - local server entrypoint
    import uvicorn

    uvicorn.run("dashboard.api:app", host="127.0.0.1", port=8080, reload=True)
