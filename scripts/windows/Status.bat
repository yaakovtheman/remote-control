@echo off
setlocal

cd /d "%~dp0\..\.."
call "scripts\windows\StartControl.bat" --status
echo.
rem When set (e.g. by ControlCenterGui.ps1), skip pause so the GUI is not blocked
if /I not "%CONTROL_NONINTERACTIVE%"=="1" pause
exit /b 0