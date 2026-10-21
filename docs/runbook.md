# Run and test Fridgi

Use Python 3.13 and Node 22.12+ with npm. Run all commands from the repository root. No account or API key is needed for the demo or the automated checks.

## Install and start the demo

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps -e ./backend
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run build
.\.venv\Scripts\python.exe scripts/run_demo.py
```

Linux/macOS:

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.lock
.venv/bin/python -m pip install --no-deps -e ./backend
npm --prefix frontend ci
npm --prefix frontend run build
.venv/bin/python scripts/run_demo.py
```

Open http://127.0.0.1:8010. The demo serves the interface and the API together and stores data in `.local-demo/pantry.db`, which survives restarts. Stop it with Ctrl+C. Rebuild the frontend after changing frontend code.

## Automated checks

Windows (on Linux/macOS use `.venv/bin/python` and `npm`):

```powershell
.\.venv\Scripts\python.exe -m ruff check backend qa/automation scripts
.\.venv\Scripts\python.exe -m pytest backend/tests -q
npm.cmd --prefix qa/api ci
.\.venv\Scripts\python.exe scripts/check_api.py
.\.venv\Scripts\python.exe -m pip install -r qa/automation/requirements.txt
$env:BROWSERS = 'chrome,firefox'
.\.venv\Scripts\python.exe -m pytest qa/automation -q
```

- `backend/tests`: unit and API tests with temporary databases and fake recipe providers.
- `scripts/check_api.py`: runs the Postman collection with Newman against a temporary offline server.
- `qa/automation`: three Selenium workflows (pantry persistence, preferences/exclusions, the BUG-001 layout regression). The frontend must be built first. On failure, a screenshot, page HTML and server log are saved under `test-results/`.

GitHub Actions runs the same checks on every push and pull request (Chrome only).

## Postman

Import `qa/api/Fridgi.postman_collection.json` and `qa/api/Local.postman_environment.json`, start the demo, select the environment and run the collection in order. It creates a test ingredient and deletes it at the end. It checks status codes, response fields, the `Cache-Control` header, whole-batch rejection, preferences vs. exclusions, and that a delete is still gone after a new GET.

Example request (demo running):

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8010/api/recipes/suggestions -ContentType 'application/json' -Body '{"source":"sample"}'
```

The response lists ingredients under `in_pantry` and `missing`, plus `warnings` and `rejected`.

## SQL

Open the demo database:

```powershell
.\.venv\Scripts\python.exe -m sqlite3 .local-demo/pantry.db
```

Paste a query from [pantry_checks.sql](../qa/sql/pantry_checks.sql) at the `sqlite>` prompt (not into PowerShell). Leave with `.quit`. The queries only read data.

## Optional: live recipes with Groq

Run `python -m alembic -c backend/alembic.ini upgrade head`, then start the backend with `scripts/start-backend-ai.ps1`. It asks for your Groq API key without saving it. In another terminal run `npm --prefix frontend run dev` and open http://127.0.0.1:5173. See `.env.example` for the settings. Never commit an API key.
