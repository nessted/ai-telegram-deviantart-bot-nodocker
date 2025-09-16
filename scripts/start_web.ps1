param()
if (Test-Path .venv\Scripts\Activate.ps1) { . .venv\Scripts\Activate.ps1 }
uvicorn app.web.main:app --host 0.0.0.0 --port 8080
