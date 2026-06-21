# DevPilot — Repository Intelligence Dashboard

DevPilot analyzes a local project folder or a public GitHub repository and produces a visual quality report: code health, documentation, testing readiness, security signals, dependency health, project structure, language breakdown, roadmap, and exports.

This release combines the provided premium frontend theme with the DevPilot cross-language analysis engine.

## Start the website — Windows

### Easiest method

Double-click:

```text
START_DEV_PILOT.bat
```

It creates an isolated `.venv` on the first run, installs the required packages automatically, chooses a free local port, and opens the browser.

### Terminal method

Open PowerShell in this extracted project folder and run:

```powershell
py run.py
```

The browser opens automatically. The default address is:

```text
http://127.0.0.1:8080
```

If port `8080` is already in use, DevPilot automatically chooses the next free port and prints the exact address in the terminal.

**Do not run** `streamlit run dashboard/app.py`. This project no longer uses Streamlit. It uses **FastAPI + the premium HTML/CSS/JavaScript dashboard**, which is started with `py run.py`.

## Analyze a project

- For a local project, paste a full folder path, such as `D:\Projects\my-app`.
- For a public repository, paste a clean GitHub URL such as `https://github.com/owner/repository`.
- Press **Enter** or click **Analyze Repository**.
- The dashboard shows real scan stages, percentage, elapsed time, ETA, completed report data, language matrix, issues, roadmap, and HTML/Markdown/JSON exports.

## CLI mode

```powershell
py run.py "D:\Projects\my-app" --export
py run.py "https://github.com/psf/requests" --export
```

## Optional test setup

```powershell
py -m pip install -r requirements-dev.txt
py -m pytest -q
```

## Architecture

```text
devpilot/
├── dashboard/
│   ├── api.py              # FastAPI API + real background progress jobs
│   ├── app.py              # Streamlit compatibility page only
│   └── serializers.py      # Analyzer report → browser payload
├── static/                 # Premium UI CSS and JavaScript
├── templates/              # Premium UI shell
├── src/devpilot/           # Multi-language analyzer
├── run.py                  # One-command automatic setup + launcher
├── START_DEV_PILOT.bat     # Double-click Windows launcher
└── tests/
```

## Supported code analysis

Python receives deeper AST checks. JavaScript, TypeScript, Java, Go, C/C++, C#, Rust, PHP, Ruby, Kotlin, Swift, Dart, SQL, Shell, PowerShell, HTML, CSS, Vue, Svelte, and other detected languages receive conservative language-aware repository quality checks. DevPilot reports engineering signals; it is not a compiler, formal static-analysis product, or security certification tool.
