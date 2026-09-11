# Roamly Windows Startup Script
# Runs backend (FastAPI on http://localhost:8000) and frontend (Vite on http://localhost:5173)

$ErrorActionPreference = "Stop"

Write-Host "Starting Roamly Backend and Frontend..." -ForegroundColor Cyan

# Root paths
$rootDir = $PSScriptRoot
$backendDir = Join-Path $rootDir "backend"
$frontendDir = Join-Path $rootDir "frontend"
$pythonExe = Join-Path $backendDir ".venv\Scripts\python.exe"

if (-not (Test-Path $pythonExe)) {
    Write-Host "Virtual environment not found in backend\.venv. Creating..." -ForegroundColor Yellow
    & "C:\Users\User\.local\bin\uv.exe" venv "$backendDir\.venv"
    & "C:\Users\User\.local\bin\uv.exe" pip install -r "$backendDir\requirements.txt" --python "$backendDir\.venv"
}

# Start backend job
$backendJob = Start-Job -ScriptBlock {
    param($dir, $py)
    Set-Location $dir
    & $py -m uvicorn app.main:app --host 0.0.0.0 --port 8000
} -ArgumentList $backendDir, $pythonExe

Write-Host "Backend server started on http://localhost:8000" -ForegroundColor Green

# Start frontend job
$frontendJob = Start-Job -ScriptBlock {
    param($dir)
    Set-Location $dir
    npm run dev -- --host 0.0.0.0 --port 5173
} -ArgumentList $frontendDir

Write-Host "Frontend server started on http://localhost:5173" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop both servers." -ForegroundColor Yellow

try {
    while ($true) {
        Receive-Job -Job $backendJob -ErrorAction SilentlyContinue | Write-Host
        Receive-Job -Job $frontendJob -ErrorAction SilentlyContinue | Write-Host
        Start-Sleep -Seconds 1
    }
} finally {
    Write-Host "Stopping servers..." -ForegroundColor Red
    Stop-Job $backendJob -ErrorAction SilentlyContinue
    Remove-Job $backendJob -ErrorAction SilentlyContinue
    Stop-Job $frontendJob -ErrorAction SilentlyContinue
    Remove-Job $frontendJob -ErrorAction SilentlyContinue
}

