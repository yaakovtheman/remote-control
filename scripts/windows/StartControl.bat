@echo off
setlocal EnableExtensions

cd /d "%~dp0\..\.."
set "ROOT_DIR=%CD%"
set "APP_DIR=%ROOT_DIR%\app"
set "LOG_DIR=%ROOT_DIR%\logs"
set "VENV_PY=%ROOT_DIR%\.venv\Scripts\python.exe"
set "MEDIAMTX_EXE=%ROOT_DIR%\bin\windows\mediamtx.exe"
set "MEDIAMTX_CFG=%APP_DIR%\mediamtx.yml"
set "FIND_CAMERAS_PY=%APP_DIR%\find_cameras.py"
set "REMOTE_PI_PY=%APP_DIR%\remote_pi_client.py"
set "SETTINGS_PY=%APP_DIR%\settings_server.py"

set "CAM_USER=admin"
set "CAM_PASS=Aa123456!"

echo ======================================
echo Starting Control
echo Root: %ROOT_DIR%
echo ======================================
echo.

if not exist "%VENV_PY%" (
    echo ERROR: venv python not found:
    echo %VENV_PY%
    goto :fail
)

if not exist "%SETTINGS_PY%" (
    echo ERROR: settings_server.py not found:
    echo %SETTINGS_PY%
    goto :fail
)

if not exist "%REMOTE_PI_PY%" (
    echo ERROR: remote_pi_client.py not found:
    echo %REMOTE_PI_PY%
    goto :fail
)

if not exist "%FIND_CAMERAS_PY%" (
    echo ERROR: find_cameras.py not found:
    echo %FIND_CAMERAS_PY%
    goto :fail
)

if not exist "%MEDIAMTX_EXE%" (
    echo ERROR: mediamtx.exe not found:
    echo %MEDIAMTX_EXE%
    goto :fail
)

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

del /q "%LOG_DIR%\remote_pi_client.log" 2>nul
del /q "%LOG_DIR%\settings_server.log" 2>nul
del /q "%LOG_DIR%\mediamtx.log" 2>nul
del /q "%APP_DIR%\status.json" 2>nul
del /q "%TEMP%\control_cameras.json" 2>nul

echo Running camera scan...
"%VENV_PY%" "%FIND_CAMERAS_PY%" > "%TEMP%\control_cameras.json"
if errorlevel 1 (
    echo WARNING: camera scan failed. Continuing anyway.
) else (
    echo Building mediamtx.yml...
    "%VENV_PY%" -c "import json, pathlib; p=pathlib.Path(r'%TEMP%\control_cameras.json'); data=json.loads(p.read_text(encoding='utf-8')); cams=data.get('cameras', []); out=pathlib.Path(r'%MEDIAMTX_CFG%'); lines=['paths:']; i=1; user=r'%CAM_USER%'; pw=r'%CAM_PASS%'; [lines.extend([f'  cam{i}:', f'    source: rtsp://{user}:{pw}@{cam.get(\"ip\")}:554/profile1', '    rtspTransport: tcp']) or globals().__setitem__('i', i+1) for cam in cams if cam.get('ip')]; out.write_text('\n'.join(lines)+'\n', encoding='utf-8')"
    if errorlevel 1 (
        echo ERROR: failed to build mediamtx.yml
        goto :fail
    )
)

echo.
echo Starting settings_server.py ...
start "SettingsServer" cmd /k ""%VENV_PY%" "%SETTINGS_PY%""

echo Starting remote_pi_client.py ...
start "RemotePiClient" cmd /k ""%VENV_PY%" "%REMOTE_PI_PY%""

echo Starting mediamtx.exe ...
start "MediaMTX" cmd /k ""%MEDIAMTX_EXE%" "%MEDIAMTX_CFG%""

echo.
echo Waiting 5 seconds...
timeout /t 5 /nobreak >nul

echo.
echo Testing web server...
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing 'http://127.0.0.1:8088' -TimeoutSec 3; Write-Host ('HTTP ' + $r.StatusCode) } catch { Write-Host ('WEB ERROR: ' + $_.Exception.Message) }"

echo.
echo Try this in browser:
echo http://127.0.0.1:8088
echo.
pause
exit /b 0

:fail
echo.
echo Start failed.
pause
exit /b 1