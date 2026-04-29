@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
title מרכז בקרה - Control

cd /d "%~dp0\..\.."
set "ROOT_DIR=%CD%"

call :banner
call :pulse "בודק מצב מערכת"
call :detect_running

if "!RUNNING_COUNT!"=="0" (
    echo.
    echo [🤖] לא זוהו שירותים פעילים - מתחיל אוטומטית...
    echo.
    call "scripts\windows\StartControl.bat"
    goto :eof
)

:menu
cls
call :banner
call :status_he
echo.
echo [🎛️] מה תרצה לעשות?
echo   [1] 🚀 התחלה (Start)
echo   [2] 🧾 סטטוס (Status)
echo   [3] ⏹️ עצירה (Stop)
echo   [4] 🔁 ריסטארט (Stop + Start)
echo   [5] 🧹 ניקוי רוחות (Cleanup Ghosts)
echo   [6] ❌ יציאה
echo.
set /p "CHOICE=הכנס מספר 1-6 ולחץ Enter: "

if "%CHOICE%"=="1" goto :do_start
if "%CHOICE%"=="2" goto :do_status
if "%CHOICE%"=="3" goto :do_stop
if "%CHOICE%"=="4" goto :do_restart
if "%CHOICE%"=="5" goto :do_cleanup
if "%CHOICE%"=="6" goto :done

echo.
echo [⚠️] בחירה לא תקינה.
timeout /t 1 /nobreak >nul
goto :menu

:do_start
echo.
call :pulse "מפעיל מערכת"
call "scripts\windows\StartControl.bat"
goto :menu

:do_status
echo.
call :pulse "אוסף סטטוס"
call "scripts\windows\StartControl.bat" --status
echo.
pause
goto :menu

:do_stop
echo.
call :pulse "עוצר שירותים"
call "scripts\windows\StartControl.bat" --stop
echo.
pause
goto :menu

:do_restart
echo.
call :pulse "מבצע ריסטארט"
call "scripts\windows\StartControl.bat" --stop
call :pulse "מעלה מערכת מחדש"
call "scripts\windows\StartControl.bat"
goto :menu

:do_cleanup
echo.
call :pulse "מנקה תהליכי רפאים"
call "scripts\windows\StartControl.bat" --cleanup
echo.
pause
goto :menu

:done
echo.
echo [👋] להתראות.
exit /b 0

:detect_running
set "RUNNING_COUNT=0"
for /f "usebackq delims=" %%N in (`powershell -NoProfile -Command "$count=0; $count += @(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" ^| Where-Object { $_.CommandLine -like '*remote_pi_client.py*' }).Count; $count += @(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" ^| Where-Object { $_.CommandLine -like '*settings_server.py*' }).Count; $count += @(Get-Process -Name 'mediamtx' -ErrorAction SilentlyContinue).Count; Write-Output $count"`) do set "RUNNING_COUNT=%%N"
if not defined RUNNING_COUNT set "RUNNING_COUNT=0"
exit /b 0

:status_he
call :detect_running
echo ************************************************************
echo * ⭐ מרכז בקרה - מצב נוכחי
echo ************************************************************
echo * תיקיה: %ROOT_DIR%
if "!RUNNING_COUNT!"=="0" (
  echo * מצב כללי: ⛔ לא פעיל
) else (
  echo * מצב כללי: ✅ פעיל ^(!RUNNING_COUNT! תהליכים^)
)
echo ************************************************************
echo.
call :line_status "RemotePiClient" "remote_pi_client.py"
call :line_status "SettingsServer" "settings_server.py"
call :line_status_mediamtx
exit /b 0

:line_status
set "LABEL=%~1"
set "PATTERN=%~2"
set "FOUND=0"
for /f "usebackq delims=" %%X in (`powershell -NoProfile -Command "$n=@(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" ^| Where-Object { $_.CommandLine -like '*%PATTERN%*' }).Count; Write-Output $n"`) do set "FOUND=%%X"
if "%FOUND%"=="0" (
  echo [⛔] %LABEL%: לא רץ
) else (
  echo [✅] %LABEL%: רץ ^(%FOUND% עותקים^)
)
exit /b 0

:line_status_mediamtx
set "FOUND=0"
for /f "usebackq delims=" %%X in (`powershell -NoProfile -Command "$n=@(Get-Process -Name 'mediamtx' -ErrorAction SilentlyContinue).Count; Write-Output $n"`) do set "FOUND=%%X"
if "%FOUND%"=="0" (
  echo [⛔] MediaMTX: לא רץ
) else (
  echo [✅] MediaMTX: רץ ^(%FOUND% עותקים^)
)
exit /b 0

:banner
echo ************************************************************
echo * 🚜 CONTROL CENTER - חלון ניהול אחד
echo * התחלה / סטטוס / עצירה / ניקוי רוחות
echo ************************************************************
exit /b 0

:pulse
set "MSG=%~1"
set /a N=0
:pulse_loop
set /a N+=1
set "DOTS="
for /L %%A in (1,1,!N!) do set "DOTS=!DOTS!•"
if !N! GTR 3 set "N=0" & set "DOTS="
<nul set /p "=. ⏳ !MSG! !DOTS!`r"
ping 127.0.0.1 -n 2 >nul
if !N! LSS 3 goto pulse_loop
echo.
exit /b 0
