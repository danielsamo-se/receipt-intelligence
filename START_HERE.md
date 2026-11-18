# Receipt Intelligence

The merchant-facing prototype is in **[app/](app/README.md)**. The original experiment README, taxonomy, data, caches and provenance are preserved unchanged.

From this project directory, use two PowerShell terminals:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\app\start-backend.ps1
```

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\app\start-frontend.ps1
```

Open **http://127.0.0.1:5173**. All classification behavior uses existing cached Jev responses; runtime requires no internet or API key.

For the simplest offline presentation, the built frontend is also served by FastAPI at **http://127.0.0.1:8000**. Run `app/build-frontend.ps1` before starting the backend to rebuild it. See [the application README](app/README.md) for setup, the exact demo sequence, tests, architecture and limitations.
