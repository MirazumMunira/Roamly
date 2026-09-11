$backendDir = Join-Path $PSScriptRoot "backend"
$pythonExe = Join-Path $backendDir ".venv\Scripts\python.exe"
Set-Location $backendDir
& $pythonExe -m uvicorn app.main:app --reload --port 8000

