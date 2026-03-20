@echo off
setlocal

cd /d "%~dp0\..\.."
set "ROOT_DIR=%CD%"

echo ======================================
echo Stopping Control
echo Root: %ROOT_DIR%
echo ======================================
echo.

taskkill /F /IM mediamtx.exe >nul 2>nul
wmic process where "CommandLine like '%%remote_pi_client.py%%'" delete >nul 2>nul
wmic process where "CommandLine like '%%settings_server.py%%'" delete >nul 2>nul

echo Done.
echo.
pause
exit /b 0
