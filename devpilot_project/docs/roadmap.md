# DevPilot Roadmap

## Completed

- Scan local folders and public GitHub repositories.
- Detect a language mix across backend, frontend, scripts, and data files.
- Score structure, code quality, README quality, dependencies, testing readiness, and security warnings.
- Use Python AST analysis where applicable and neutral language-aware heuristics for supported non-Python languages.
- Serve the supplied HTML/CSS/JavaScript dashboard with FastAPI.
- Show real background-job progress, estimated duration, elapsed time, and audit events.
- Export JSON, Markdown, and standalone HTML reports.

## Next improvements

- Persist audit history in SQLite instead of browser-session memory.
- Add GitHub OAuth and private-repository support.
- Add optional tools such as ESLint, TypeScript, Ruff, mypy, Semgrep, or language servers when those tools are available locally.
- Add comparison views between repository audits.
- Add AI-assisted README and improvement-plan drafting with a user-selected provider.
