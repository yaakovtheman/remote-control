@echo off
setlocal

cd /d "%~dp0\..\.."
set "ROOT_DIR=%CD%"
set "LOG_DIR=%ROOT_DIR%\logs"

echo ======================================
echo Control stack status
echo Root: %ROOT_DIR%
echo ======================================
echo.

echo == Python / app processes ==
wmic process where "CommandLine like '%%remote_pi_client.py%%'" get ProcessId,Name,CommandLine 2>nul
echo.
wmic process where "CommandLine like '%%settings_server.py%%'" get ProcessId,Name,CommandLine 2>nul
echo.

echo == MediaMTX ==
tasklist /FI "IMAGENAME eq mediamtx.exe"
echo.

echo == Listening ports ==
netstat -ano | findstr ":7000 "
netstat -ano | findstr ":8088 "
netstat -ano | findstr ":8889 "
echo.

echo == Recent logs ==
if exist "%LOG_DIR%\remote_pi_client.log" (
    echo --- remote_pi_client.log ---
    powershell -NoProfile -Command "Get-Content -Path '%LOG_DIR%\remote_pi_client.log' -Tail 8"
    echo.
)

if exist "%LOG_DIR%\settings_server.log" (
    echo --- settings_server.log ---
    powershell -NoProfile -Command "Get-Content -Path '%LOG_DIR%\settings_server.log' -Tail 8"
    echo.
)

if exist "%LOG_DIR%\mediamtx.log" (
    echo --- mediamtx.log ---
    powershell -NoProfile -Command "Get-Content -Path '%LOG_DIR%\mediamtx.log' -Tail 8"
    echo.
)

pause
exit /b 0