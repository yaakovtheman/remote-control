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
echo   (1) Start
echo   (2) Status
echo   (3) Stop
echo   (4) Restart (Stop + Start)
echo   (5) Cleanup Ghost Processes
echo   (6) Exit
echo.
set "CHOICE="
set /p "CHOICE=Enter 1-6 and press Enter: "

if "%CHOICE%"=="1" goto :do_start
if "%CHOICE%"=="2" goto :do_status
if "%CHOICE%"=="3" goto :do_stop
if "%CHOICE%"=="4" goto :do_restart
if "%CHOICE%"=="5" goto :do_cleanup
if "%CHOICE%"=="6" goto :done

echo.
echo [!] Invalid selection.
timeout /t 1 /nobreak >nul
goto :menu

:do_start
echo.
echo [>] Starting system...
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

:do_restart
echo.
echo [~] Restarting services...
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
