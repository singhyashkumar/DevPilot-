"""Smoke tests for the FastAPI dashboard integration."""

from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from dashboard.app import app


def test_web_api_runs_a_real_local_audit(tmp_path: Path) -> None:
    """The supplied browser UI API must return a real multi-language report."""
    repo = tmp_path / "sample-web-repo"
    repo.mkdir()
    (repo / "README.md").write_text(
        "# Sample\n\n## Features\n\n## Installation\n\n## Usage\n", encoding="utf-8"
    )
    (repo / "app.js").write_text("export function add(a, b) { return a + b; }\n", encoding="utf-8")
    (repo / "package.json").write_text('{"name":"sample-web-repo","dependencies":{}}', encoding="utf-8")

    with TestClient(app) as client:
        created = client.post("/api/analyze", json={"source": str(repo), "analysis_type": "local"})
        assert created.status_code == 202
        job_id = created.json()["jobId"]
        payload = _wait_for_report(client, job_id)

        assert payload["repoName"] == "sample-web-repo"
        assert payload["analysis"]["languageLabel"] == "JavaScript"
        assert payload["breakdown"]["codeQuality"] is not None
        assert payload["languages"][0]["name"] == "JavaScript"
        exported = client.get(f"/api/jobs/{job_id}/export/markdown")
        assert exported.status_code == 200
        assert "DevPilot Repository Report" in exported.text


def _wait_for_report(client: TestClient, job_id: str) -> dict[str, object]:
    """Poll a background audit with a small upper bound for test safety."""
    for _ in range(80):
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        state = response.json()
        if state["state"] == "completed":
            return state["report"]
        assert state["state"] != "failed", state
        time.sleep(0.025)
    raise AssertionError("The local DevPilot API audit did not finish in time.")
