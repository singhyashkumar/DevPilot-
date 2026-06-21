# DevPilot — Repository Intelligence Dashboard

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)

**DevPilot** is an intelligent code analysis dashboard that evaluates local projects or public GitHub repositories, delivering comprehensive visual reports on code health, documentation quality, testing readiness, security signals, dependency health, project structure, language distribution, and actionable roadmaps.

This release integrates a premium frontend theme with DevPilot's powerful cross-language analysis engine.

---

## 🚀 Quick Start

### Windows Users

#### Option 1: One-Click Launch (Recommended)

Simply double-click the launcher:

```batch
START_DEV_PILOT.bat
```

On first run, this script will:
- Create an isolated virtual environment (`.venv`)
- Install all required dependencies automatically
- Select an available local port
- Open your default browser

#### Option 2: Terminal Launch

Open PowerShell in the project directory and execute:

```powershell
py run.py
```

The dashboard will open automatically at:

```
http://127.0.0.1:8080
```

> **Note:** If port `8080` is occupied, DevPilot automatically selects the next available port and displays the exact URL in the terminal.

⚠️ **Important:** Do not run `streamlit run dashboard/app.py`. This project uses **FastAPI + Premium HTML/CSS/JavaScript Dashboard**, launched exclusively via `py run.py`.

---

## 📊 Analyze a Project

DevPilot supports both local directories and public GitHub repositories:

1. **Local Project:** Enter the full path, e.g., `D:\Projects\my-app`
2. **GitHub Repository:** Paste a clean URL, e.g., `https://github.com/owner/repository`
3. Click **Analyze Repository** or press **Enter**

The dashboard displays:
- ✅ Real-time scan progress (percentage, elapsed time, ETA)
- ✅ Comprehensive report metrics
- ✅ Language distribution matrix
- ✅ Identified issues and recommendations
- ✅ Development roadmap
- ✅ Export options (HTML, Markdown, JSON)

---

## 💻 Command-Line Interface (CLI)

Run analyses directly from the terminal:

```powershell
# Analyze a local project with export
py run.py "D:\Projects\my-app" --export

# Analyze a GitHub repository with export
py run.py "https://github.com/psf/requests" --export
```

---

## 🧪 Development & Testing

Install development dependencies and run tests:

```powershell
# Install dev requirements
py -m pip install -r requirements-dev.txt

# Run test suite
py -m pytest -q
```

---

## 🏗️ Project Architecture

```
devpilot/
├── dashboard/
│   ├── api.py              # FastAPI backend + real-time background jobs
│   ├── app.py              # Streamlit compatibility layer (legacy)
│   └── serializers.py      # Report serialization for browser payloads
├── static/                 # Premium UI assets (CSS, JavaScript)
├── templates/              # Premium UI HTML templates
├── src/devpilot/           # Multi-language analysis engine
├── run.py                  # Unified setup script + application launcher
├── START_DEV_PILOT.bat     # Windows one-click launcher
└── tests/                  # Test suite
```

---

## 🔍 Supported Languages & Analysis

DevPilot provides **deep AST-based analysis** for Python and **conservative language-aware quality checks** for:

| Category | Languages |
|----------|-----------|
| **Web** | JavaScript, TypeScript, HTML, CSS, Vue, Svelte, PHP |
| **Systems** | Rust, C, C++, Go |
| **Enterprise** | Java, C#, Kotlin, Swift |
| **Scripting** | Ruby, Shell, PowerShell |
| **Data** | SQL, Dart |

> **Disclaimer:** DevPilot reports engineering signals and code quality indicators. It is **not** a compiler, formal static-analysis tool, or security certification product.

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request or open an Issue for bugs, feature requests, or improvements.

---

<p align="center">
  <strong>Built with ❤️ using FastAPI & Premium UI Components</strong>
</p>
