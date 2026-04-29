@echo off
setlocal

cd /d "%~dp0\..\.."
call "scripts\windows\StartControl.bat" --cleanup
echo.
pause
exit /b 0
