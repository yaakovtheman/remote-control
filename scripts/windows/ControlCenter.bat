@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Control Center

cd /d "%~dp0\..\.."
set "ROOT_DIR=%CD%"

:menu
cls
call :banner
echo.
echo [#] Choose an action:
echo   (1) Quick Start  -- use saved Pi + camera IPs, no network scan
echo   (2) Full Start   -- scan network for Pi and cameras first
echo   (3) Status
echo   (4) Stop
echo   (5) Restart (Stop + Quick Start)
echo   (6) Full Restart (Stop + Full Start)
echo   (7) Cleanup Ghost Processes
echo   (8) Exit
echo.
set "CHOICE="
set /p "CHOICE=Enter 1-8 and press Enter: "

if "%CHOICE%"=="1" goto :do_quick_start
if "%CHOICE%"=="2" goto :do_start
if "%CHOICE%"=="3" goto :do_status
if "%CHOICE%"=="4" goto :do_stop
if "%CHOICE%"=="5" goto :do_quick_restart
if "%CHOICE%"=="6" goto :do_restart
if "%CHOICE%"=="7" goto :do_cleanup
if "%CHOICE%"=="8" goto :done

echo.
echo [!] Invalid selection.
timeout /t 1 /nobreak >nul
goto :menu

:do_quick_start
echo.
echo [>] Quick start (no scan)...
call "scripts\windows\StartControl.bat" --no-scan
echo.
echo [i] Returned to Control Center.
pause
goto :menu

:do_start
echo.
echo [>] Full start (with scan)...
call "scripts\windows\StartControl.bat"
echo.
echo [i] Returned to Control Center.
pause
goto :menu

:do_status
echo.
echo [i] Collecting status...
call "scripts\windows\StartControl.bat" --status
echo.
echo [i] Returned to Control Center.
pause
goto :menu

:do_stop
echo.
echo [x] Stopping services...
call "scripts\windows\StartControl.bat" --stop
echo.
echo [i] Returned to Control Center.
pause
goto :menu

:do_quick_restart
echo.
echo [~] Restarting (quick, no scan)...
call "scripts\windows\StartControl.bat" --stop
call "scripts\windows\StartControl.bat" --no-scan
echo.
echo [i] Returned to Control Center.
pause
goto :menu

:do_restart
echo.
echo [~] Full restart (with scan)...
call "scripts\windows\StartControl.bat" --stop
call "scripts\windows\StartControl.bat"
echo.
echo [i] Returned to Control Center.
pause
goto :menu

:do_cleanup
echo.
echo [!] Cleaning ghost processes...
call "scripts\windows\StartControl.bat" --cleanup
echo.
echo [i] Returned to Control Center.
pause
goto :menu

:done
echo.
echo [q] Goodbye.
pause
exit /b 0

:banner
echo ************************************************************
echo * CONTROL CENTER - SINGLE WINDOW MANAGER
echo * Root: %ROOT_DIR%
echo ************************************************************
exit /b 0
