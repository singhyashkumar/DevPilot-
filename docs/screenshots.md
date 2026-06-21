# Dashboard visual guide

The web dashboard runs on FastAPI and is started with:

```powershell
py run.py
```

Open `http://127.0.0.1:8080`, scan a local repository or public GitHub URL, and capture screenshots after the audit completes.

Recommended GitHub README screenshots:

1. **Audit launch screen:** GitHub/local input tabs and repository entry area.
2. **Live analysis state:** real percentage, analyzer steps, ETA, elapsed time, and activity events.
3. **Overall score:** animated score circle and the six score-breakdown cards.
4. **Language Health Matrix:** detected-language cards with score bars, LOC, functions, comments, and findings.
5. **Report detail:** roadmap timeline and issue tabs.

Store final PNGs/GIFs in this `docs/` folder and reference them from the project README before publishing.
