@echo off
setlocal

cd /d "%~dp0\..\.."
call "scripts\windows\StartControl.bat" --status
echo.
pause
exit /b 0