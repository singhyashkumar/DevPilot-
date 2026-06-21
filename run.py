"""Reliable DevPilot launcher.

Usage:
    py run.py                            # starts the premium web dashboard
    py run.py --web                      # same as above
    py run.py "D:/Projects/my-app" --export

On a first run, missing web dependencies are installed automatically from
``requirements.txt``. The launcher also selects a free local port so an
occupied port never turns into an opaque uvicorn traceback.
"""

from __future__ import annotations

import importlib
import os
import socket
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

RUNTIME_MODULES = {
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "git": "GitPython",
}
DEFAULT_PORT = 8080
PORT_SEARCH_LIMIT = 20


def _missing_runtime_dependencies() -> list[str]:
    """Return missing runtime modules without crashing at import time."""
    missing: list[str] = []
    for module_name, package_name in RUNTIME_MODULES.items():
        try:
            importlib.import_module(module_name)
        except ModuleNotFoundError:
            missing.append(package_name)
    return missing


def _install_runtime_dependencies() -> bool:
    """Install runtime dependencies for a first-run dashboard launch."""
    missing = _missing_runtime_dependencies()
    if not missing:
        return True

    print("\n[DevPilot] First-run setup: installing required dashboard packages...")
    print(f"[DevPilot] Missing: {', '.join(missing)}")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")]
        )
    except subprocess.CalledProcessError as exc:
        print("\n[DevPilot] Setup could not complete automatically.")
        print("Run this command manually, then start DevPilot again:")
        print(f'  {sys.executable} -m pip install -r requirements.txt')
        print(f"Installer exit code: {exc.returncode}")
        return False

    still_missing = _missing_runtime_dependencies()
    if still_missing:
        print("\n[DevPilot] Packages installed, but Python still cannot import:", ", ".join(still_missing))
        print("Close this terminal, open a new one in the project folder, then run: py run.py")
        return False
    return True


def _configured_port() -> int:
    """Read an optional port override while rejecting invalid values early."""
    raw = os.getenv("DEVPILOT_PORT", str(DEFAULT_PORT)).strip()
    try:
        value = int(raw)
    except ValueError:
        print(f"[DevPilot] Ignoring invalid DEVPILOT_PORT={raw!r}; using {DEFAULT_PORT}.")
        return DEFAULT_PORT
    return value if 1 <= value <= 65535 else DEFAULT_PORT


def _port_is_available(port: int) -> bool:
    """Check whether the local address can be bound before starting uvicorn."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _choose_port() -> int:
    """Prefer the requested port, then choose the nearest available port."""
    preferred = _configured_port()
    for port in range(preferred, min(65536, preferred + PORT_SEARCH_LIMIT)):
        if _port_is_available(port):
            if port != preferred:
                print(f"[DevPilot] Port {preferred} is busy; using available port {port} instead.")
            return port
    raise RuntimeError(
        f"No free local port was found between {preferred} and {preferred + PORT_SEARCH_LIMIT - 1}. "
        "Close another local server or set DEVPILOT_PORT to a different value."
    )


def _open_browser(url: str) -> None:
    """Open the local dashboard after uvicorn has had a moment to bind."""
    if os.getenv("DEVPILOT_NO_BROWSER", "").strip().casefold() in {"1", "true", "yes"}:
        return
    try:
        webbrowser.open(url)
    except Exception:
        # The terminal URL remains enough for headless or restricted systems.
        pass


def start_web_dashboard() -> None:
    """Start the FastAPI dashboard at a free, predictable local address."""
    if not _install_runtime_dependencies():
        raise SystemExit(1)

    import uvicorn

    try:
        port = _choose_port()
    except RuntimeError as exc:
        print(f"[DevPilot] {exc}")
        raise SystemExit(1) from exc

    url = f"http://127.0.0.1:{port}"
    print("\n[DevPilot] Starting the premium dashboard...")
    print(f"[DevPilot] Open: {url}")
    print("[DevPilot] Press Ctrl+C here when you want to stop the server.\n")
    threading.Timer(0.8, _open_browser, args=(url,)).start()
    # Do not use reload here: it starts a second process and can confuse a
    # first-time Windows user. Development reload is available through uvicorn.
    uvicorn.run("dashboard.api:app", host="127.0.0.1", port=port, reload=False)


def run_cli() -> None:
    """Delegate source-based commands to the production analyzer CLI."""
    missing = _missing_runtime_dependencies()
    if missing:
        print("[DevPilot] Preparing the analyzer for first use...")
        if not _install_runtime_dependencies():
            raise SystemExit(1)
    from devpilot.main import cli

    cli()


if __name__ == "__main__":
    if len(sys.argv) == 1 or sys.argv[1] in {"--web", "web"}:
        if len(sys.argv) > 1:
            sys.argv.pop(1)
        start_web_dashboard()
    else:
        run_cli()
