"""Compatibility entrypoint for people who still run ``streamlit run dashboard/app.py``.

DevPilot's merged dashboard uses FastAPI + the uploaded HTML/CSS/JavaScript UI.
The real application object lives in :mod:`dashboard.api`.  This module prevents
an opaque traceback when an older Streamlit command is used.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _called_by_streamlit() -> bool:
    """Return whether this module is being executed by the Streamlit CLI."""
    command = " ".join(sys.argv).casefold()
    return "streamlit" in command


if _called_by_streamlit():
    # No FastAPI import happens in this branch.  It therefore gives a useful
    # compatibility page even before the FastAPI dependencies are installed.
    import streamlit as st

    st.set_page_config(page_title="DevPilot launcher", page_icon="🚀", layout="centered")
    st.title("DevPilot has moved to the modern dashboard")
    st.info(
        "This version is no longer a Streamlit project. The premium uploaded UI runs "
        "through FastAPI, so `streamlit run dashboard/app.py` is not the correct command."
    )
    st.code("py run.py", language="powershell")
    st.write("Run that command from the DevPilot project folder, then open:")
    st.code("http://127.0.0.1:8080", language="text")
    st.caption("Use START_DEV_PILOT.bat for the one-click launcher. It creates an isolated .venv and installs dependencies automatically.")
else:
    # Preserve the historical import path used by tests and integrations.
    from dashboard.api import app
