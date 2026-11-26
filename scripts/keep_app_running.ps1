# Starts the SocioBridge-TB Streamlit app on http://localhost:8501 if it is not already running.
# Run by the Windows scheduled task "SocioBridge-TB app" at logon and every 5 minutes
# (so the app comes back after sleep, restart or a crash). Safe to run by hand at any time.
$root = Split-Path -Parent $PSScriptRoot
$port = 8501
$log  = Join-Path $root "results\app_server.log"

$up = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($up) { exit 0 }   # already running

$python  = Join-Path $root ".venv\Scripts\python.exe"
$argList = "-m streamlit run app.py --server.headless true --server.port $port --browser.gatherUsageStats false"
try {
    Start-Process -FilePath $python -ArgumentList $argList -WorkingDirectory $root -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $root "results\app_stdout.log") `
        -RedirectStandardError  (Join-Path $root "results\app_stderr.log") -ErrorAction Stop
    Add-Content -Path $log -Value "$(Get-Date -Format s)  app was down - started"
} catch {
    Add-Content -Path $log -Value "$(Get-Date -Format s)  start FAILED: $_"
}
