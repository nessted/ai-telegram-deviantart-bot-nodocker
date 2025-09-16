param()
if (Test-Path .venv\Scripts\Activate.ps1) { . .venv\Scripts\Activate.ps1 }
Start-Process powershell -ArgumentList '-NoExit','-Command','uvicorn app.web.main:app --host 0.0.0.0 --port 8080'
Start-Process powershell -ArgumentList '-NoExit','-Command','python -m app.bot'
Write-Host "Processes started in separate PowerShell windows."
