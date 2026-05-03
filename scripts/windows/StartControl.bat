@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title Control Launcher - Windows

cd /d "%~dp0\..\.."
set "ROOT_DIR=%CD%"
set "APP_DIR=%ROOT_DIR%\app"
set "LOG_DIR=%ROOT_DIR%\logs"
set "PID_DIR=%LOG_DIR%\pids"
set "VENV_PY=%ROOT_DIR%\.venv\Scripts\python.exe"
set "MEDIAMTX_EXE=%ROOT_DIR%\bin\windows\mediamtx.exe"
set "MEDIAMTX_CFG=%APP_DIR%\mediamtx.yml"
set "FIND_CAMERAS_PY=%APP_DIR%\find_cameras.py"
set "REMOTE_PI_PY=%APP_DIR%\remote_pi_client.py"
set "SETTINGS_PY=%APP_DIR%\settings_server.py"
set "CONFIG_JSON=%APP_DIR%\config.json"
set "SCAN_JSON=%TEMP%\control_cameras.json"

set "PI_IP="
set "CAM_COUNT=0"
set "SUBNETS=unknown"
set "TARGET_URL="
set "VISIBLE_MODE=0"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
if not exist "%PID_DIR%" mkdir "%PID_DIR%"

if /I "%~1"=="--status" goto :status
if /I "%~1"=="--stop" goto :stop
if /I "%~1"=="--cleanup" goto :cleanup
if /I "%~1"=="--visible" set "VISIBLE_MODE=1"

call :banner
call :step "Environment checks"
if not exist "%VENV_PY%" call :fail_with "venv python not found: %VENV_PY%"
if not exist "%SETTINGS_PY%" call :fail_with "settings_server.py not found: %SETTINGS_PY%"
if not exist "%REMOTE_PI_PY%" call :fail_with "remote_pi_client.py not found: %REMOTE_PI_PY%"
if not exist "%FIND_CAMERAS_PY%" call :fail_with "find_cameras.py not found: %FIND_CAMERAS_PY%"
if not exist "%MEDIAMTX_EXE%" call :fail_with "mediamtx.exe not found: %MEDIAMTX_EXE%"
call :ok "Required files found"

call :cleanup_silent
call :stop_silent
del /q "%LOG_DIR%\remote_pi_client.log" 2>nul
del /q "%LOG_DIR%\settings_server.log" 2>nul
del /q "%LOG_DIR%\mediamtx.log" 2>nul
del /q "%APP_DIR%\status.json" 2>nul
del /q "%SCAN_JSON%" 2>nul

call :step "Find Raspberry Pi and update config.json"
call :pulse "Running Pi scan"
"%VENV_PY%" "%FIND_CAMERAS_PY%" --pi --pretty
if errorlevel 1 (call :warn "Pi scan returned error, continuing")

for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "$cfg = Get-Content -Raw -Path '%CONFIG_JSON%' | ConvertFrom-Json; if ($null -ne $cfg.server_ip) { [string]$cfg.server_ip }"`) do set "PI_IP=%%I"
if defined PI_IP (call :ok "Pi IP: !PI_IP!") else (call :warn "No Pi IP in config.json")

call :step "Scan cameras and build mediamtx.yml"
call :pulse "Searching cameras in network"
"%VENV_PY%" "%FIND_CAMERAS_PY%" --cam > "%SCAN_JSON%"
if errorlevel 1 (
    call :warn "Camera scan failed - writing fallback config"
    > "%MEDIAMTX_CFG%" echo paths: {}
    if errorlevel 1 call :fail_with "Failed to create fallback mediamtx.yml"
    set "CAM_COUNT=0"
) else (
    for /f "usebackq delims=" %%C in (`powershell -NoProfile -Command "$d = Get-Content -Raw -Path '%SCAN_JSON%' | ConvertFrom-Json; if ($null -ne $d.count) { [string]$d.count } else { '0' }"`) do set "CAM_COUNT=%%C"
    for /f "usebackq delims=" %%S in (`powershell -NoProfile -Command "$d = Get-Content -Raw -Path '%SCAN_JSON%' | ConvertFrom-Json; if ($d.subnets -and $d.subnets.Count -gt 0) { ($d.subnets -join ', ') } else { 'unknown' }"`) do set "SUBNETS=%%S"
    call :info "Checked subnets: !SUBNETS!"
    call :info "Found !CAM_COUNT! cameras"
    powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT_DIR%\scripts\windows\build_mediamtx.ps1" "%SCAN_JSON%" "%CONFIG_JSON%" "%MEDIAMTX_CFG%"
    if errorlevel 1 call :fail_with "Failed to build mediamtx.yml"
    powershell -NoProfile -Command "$content = Get-Content -Path '%MEDIAMTX_CFG%' -Raw; if ([string]::IsNullOrWhiteSpace($content) -or $content -notmatch 'cam\d+:') { Set-Content -Path '%MEDIAMTX_CFG%' -Value \"paths: {}`r`n\" -Encoding UTF8 }"
)

call :step "Start services"
if "%VISIBLE_MODE%"=="1" (
    call :info "Visible mode: opening 3 service windows"
    start "SettingsServer" cmd /k ""%VENV_PY%" "%SETTINGS_PY%""
    start "RemotePiClient" cmd /k ""%VENV_PY%" "%REMOTE_PI_PY%""
    start "MediaMTX" cmd /k ""%MEDIAMTX_EXE%" "%MEDIAMTX_CFG%""
) else (
    call :info "Background mode: services run hidden, logs + pid tracked"
    call :start_hidden_py "%SETTINGS_PY%" "%LOG_DIR%\settings_server.log" "%PID_DIR%\settings_server.pid"
    call :start_hidden_py "%REMOTE_PI_PY%" "%LOG_DIR%\remote_pi_client.log" "%PID_DIR%\remote_pi_client.pid"
    call :start_hidden_exe "%MEDIAMTX_EXE%" "%MEDIAMTX_CFG%" "%LOG_DIR%\mediamtx.log" "%PID_DIR%\mediamtx.pid"
)
call :ok "Services launched"

call :step "Check web and open browser"
if defined PI_IP (set "TARGET_URL=http://!PI_IP!:8088/") else (set "TARGET_URL=http://127.0.0.1:8088/")
call :info "Target URL: !TARGET_URL!"
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing '!TARGET_URL!' -TimeoutSec 3; Write-Host ('HTTP ' + $r.StatusCode) } catch { Write-Host ('WEB ERROR: ' + $_.Exception.Message) }"
start "" "!TARGET_URL!"

echo.
echo ************************************************************
echo * Startup completed
echo * Pi IP: !PI_IP!
echo * Cameras: !CAM_COUNT!
echo * Subnets: !SUBNETS!
echo * Browser: !TARGET_URL!
echo * Logs: %LOG_DIR%
echo * Status command: scripts\windows\StartControl.bat --status
echo * Stop command:   scripts\windows\StartControl.bat --stop
echo ************************************************************
echo.
pause
exit /b 0

:status
echo.
echo ==================== CONTROL STATUS ====================
call :show_service "SettingsServer" "%PID_DIR%\settings_server.pid"
call :show_service "RemotePiClient" "%PID_DIR%\remote_pi_client.pid"
call :show_service "MediaMTX" "%PID_DIR%\mediamtx.pid"
for /f "usebackq delims=" %%I in (`powershell -NoProfile -Command "$cfg = Get-Content -Raw -Path '%CONFIG_JSON%' | ConvertFrom-Json; if ($null -ne $cfg.server_ip -and -not [string]::IsNullOrWhiteSpace([string]$cfg.server_ip)) { [string]$cfg.server_ip } else { '127.0.0.1' }"`) do set "PI_IP=%%I"
set "TARGET_URL=http://%PI_IP%:8088/"
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing '%TARGET_URL%' -TimeoutSec 3; Write-Host ('Web UI: UP (HTTP ' + $r.StatusCode + ') - %TARGET_URL%') } catch { Write-Host ('Web UI: DOWN - %TARGET_URL%') }"
echo Logs: %LOG_DIR%
echo ========================================================
exit /b 0

:stop
echo Stopping Control services...
call :stop_service "%PID_DIR%\settings_server.pid"
call :stop_service "%PID_DIR%\remote_pi_client.pid"
call :stop_service "%PID_DIR%\mediamtx.pid"
echo Done.
exit /b 0

:cleanup
echo Cleaning up ghost processes...
call :stop_silent
call :kill_ghosts
echo Cleanup completed.
exit /b 0

:stop_silent
call :stop_service "%PID_DIR%\settings_server.pid" >nul 2>&1
call :stop_service "%PID_DIR%\remote_pi_client.pid" >nul 2>&1
call :stop_service "%PID_DIR%\mediamtx.pid" >nul 2>&1
exit /b 0

:cleanup_silent
call :kill_ghosts >nul 2>&1
exit /b 0

:kill_ghosts
powershell -NoProfile -Command "$patterns=@('remote_pi_client.py','settings_server.py'); foreach($pat in $patterns){ Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like ('*' + $pat + '*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue } }; Get-Process -Name 'mediamtx' -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue"
exit /b 0

:start_hidden_py
powershell -NoProfile -Command "$p=Start-Process -FilePath '%VENV_PY%' -ArgumentList '\"%~1\"' -RedirectStandardOutput '%~2' -RedirectStandardError '%~2.err' -WindowStyle Hidden -PassThru; Set-Content -Path '%~3' -Value $p.Id"
exit /b 0

:start_hidden_exe
powershell -NoProfile -Command "$p=Start-Process -FilePath '%~1' -ArgumentList '\"%~2\"' -RedirectStandardOutput '%~3' -RedirectStandardError '%~3.err' -WindowStyle Hidden -PassThru; Set-Content -Path '%~4' -Value $p.Id"
exit /b 0

:show_service
set "SERVICE_NAME=%~1"
set "PID_FILE=%~2"
if not exist "%PID_FILE%" (
    echo %SERVICE_NAME%: DOWN (no pid file)
    exit /b 0
)
set /p PID=<"%PID_FILE%"
if not defined PID (
    echo %SERVICE_NAME%: DOWN (empty pid file)
    exit /b 0
)
tasklist /FI "PID eq %PID%" | findstr /I "%PID%" >nul
if errorlevel 1 (
    echo %SERVICE_NAME%: DOWN (stale pid %PID%)
) else (
    echo %SERVICE_NAME%: UP (pid %PID%)
)
exit /b 0

:stop_service
set "PID_FILE=%~1"
if not exist "%PID_FILE%" exit /b 0
set /p PID=<"%PID_FILE%"
if defined PID taskkill /PID %PID% /T /F >nul 2>&1
del /q "%PID_FILE%" >nul 2>&1
exit /b 0

:banner
cls
echo ************************************************************
echo * CONTROL LAUNCHER - WINDOWS
echo * Professional startup with status and service control
echo ************************************************************
echo * Project root: %ROOT_DIR%
echo ************************************************************
echo.
exit /b 0

:step
echo.
echo [*] =========================================================
echo [*] %~1
echo [*] =========================================================
exit /b 0

:ok
echo [OK] %~1
exit /b 0

:warn
echo [WARN] %~1
exit /b 0

:info
echo [INFO] %~1
exit /b 0

:pulse
set "MSG=%~1"
set /a N=0
:pulse_loop
set /a N+=1
set "STARS="
for /L %%A in (1,1,!N!) do set "STARS=!STARS!*"
if !N! GTR 3 set "N=0" & set "STARS="
echo . !MSG! !STARS!
ping 127.0.0.1 -n 2 >nul
if !N! LSS 3 goto pulse_loop
echo.
exit /b 0

:fail_with
echo.
echo ************************************************************
echo * FAIL:
echo * %~1
echo ************************************************************
echo.
pause
exit /b 1