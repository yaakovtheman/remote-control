@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0\..\.."
set "ROOT_DIR=%CD%"
set "APP_DIR=%ROOT_DIR%\app"
set "VENV_DIR=%ROOT_DIR%\.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "REQ_FILE=%ROOT_DIR%\requirements.txt"
set "MEDIAMTX_EXE=%ROOT_DIR%\bin\windows\mediamtx.exe"
set "WHEEL_DIR=%ROOT_DIR%\bin\windows\wheels"

set "PYTHON_VERSION=3.13.12"
set "PYTHON_INSTALLER=python-%PYTHON_VERSION%-amd64.exe"
set "PYTHON_LOCAL=%ROOT_DIR%\bin\windows\%PYTHON_INSTALLER%"
set "PYTHON_URL=https://www.python.org/ftp/python/%PYTHON_VERSION%/%PYTHON_INSTALLER%"
set "PYTHON_TEMP=%TEMP%\%PYTHON_INSTALLER%"

set "BASE_PY="
set "BASE_PY_ARGS="
set "PYTHON_EXE1=%LocalAppData%\Programs\Python\Python313\python.exe"
set "PYTHON_EXE2=%ProgramFiles%\Python313\python.exe"

echo ======================================
echo Control setup for Windows
echo Root: %ROOT_DIR%
echo ======================================
echo.

if not exist "%REQ_FILE%" (
    echo ERROR: requirements.txt not found:
    echo %REQ_FILE%
    pause
    exit /b 1
)

echo Checking for Python...
where py >nul 2>nul
if not errorlevel 1 (
    set "BASE_PY=py"
    set "BASE_PY_ARGS=-3.13"
)

if not defined BASE_PY (
    if exist "%PYTHON_EXE1%" (
        set "BASE_PY=%PYTHON_EXE1%"
        set "BASE_PY_ARGS="
    )
)

if not defined BASE_PY (
    if exist "%PYTHON_EXE2%" (
        set "BASE_PY=%PYTHON_EXE2%"
        set "BASE_PY_ARGS="
    )
)

if not defined BASE_PY (
    echo Python not found.

    if exist "%PYTHON_LOCAL%" (
        echo Found local Python installer:
        echo %PYTHON_LOCAL%
        set "PYTHON_SOURCE=%PYTHON_LOCAL%"
    ) else (
        echo Local installer not found.
        echo Downloading Python %PYTHON_VERSION%...
        powershell -NoProfile -ExecutionPolicy Bypass -Command ^
          "Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%PYTHON_TEMP%'"
        if errorlevel 1 (
            echo ERROR: Failed to download Python installer.
            pause
            exit /b 1
        )
        set "PYTHON_SOURCE=%PYTHON_TEMP%"
    )

    echo.
    echo Installing Python, please wait...
    "!PYTHON_SOURCE!" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_launcher=1
    if errorlevel 1 (
        echo ERROR: Python installation failed.
        pause
        exit /b 1
    )

    echo Waiting for Python installation to settle...
    timeout /t 5 /nobreak >nul

    if exist "%PYTHON_EXE1%" (
        set "BASE_PY=%PYTHON_EXE1%"
        set "BASE_PY_ARGS="
    ) else if exist "%PYTHON_EXE2%" (
        set "BASE_PY=%PYTHON_EXE2%"
        set "BASE_PY_ARGS="
    ) else (
        where py >nul 2>nul
        if not errorlevel 1 (
            set "BASE_PY=py"
            set "BASE_PY_ARGS=-3.13"
        )
    )
)

if not defined BASE_PY (
    echo ERROR: Python is still not available after installation.
    pause
    exit /b 1
)

echo Using Python: %BASE_PY%
echo.

if exist "%VENV_DIR%" (
    if not exist "%VENV_PY%" (
        echo Existing virtual environment looks broken. Recreating it...
        rmdir /s /q "%VENV_DIR%"
    )
)

if not exist "%VENV_PY%" (
    echo Creating virtual environment...
    call "%BASE_PY%" %BASE_PY_ARGS% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo Virtual environment already exists and looks valid.
)

if not exist "%VENV_PY%" (
    echo ERROR: Virtual environment python was not created:
    echo %VENV_PY%
    pause
    exit /b 1
)

echo Upgrading pip, please wait...
call "%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 (
    echo ERROR: Failed to upgrade pip.
    pause
    exit /b 1
)

echo Installing Python packages, please wait...
call "%VENV_PY%" -m pip install -r "%REQ_FILE%"
if errorlevel 1 (
    echo.
    echo Online install failed. Trying offline wheelhouse...
    if exist "%WHEEL_DIR%" (
        call "%VENV_PY%" -m pip install --no-index --find-links "%WHEEL_DIR%" -r "%REQ_FILE%"
        if errorlevel 1 (
            echo ERROR: Failed to install requirements from offline wheelhouse.
            echo Check that "%WHEEL_DIR%" contains compatible wheels for:
            echo   - flask
            echo   - pygame
            pause
            exit /b 1
        )
        echo Installed requirements from offline wheelhouse.
    ) else (
        echo ERROR: Failed to install requirements.
        echo.
        echo No internet access detected and no offline wheelhouse found at:
        echo   "%WHEEL_DIR%"
        echo.
        echo To support offline install:
        echo 1^) On an internet-connected Windows machine, create wheels:
        echo    py -3.13 -m pip download -r requirements.txt -d bin\windows\wheels
        echo 2^) Copy the project (including bin\windows\wheels^) to this machine.
        echo 3^) Run Install.bat again.
        pause
        exit /b 1
    )
)

if not exist "%ROOT_DIR%\logs" mkdir "%ROOT_DIR%\logs"

if not exist "%APP_DIR%\status.json" (
    echo {}>"%APP_DIR%\status.json"
)

if not exist "%MEDIAMTX_EXE%" (
    echo WARNING: MediaMTX not found:
    echo %MEDIAMTX_EXE%
    echo Python setup completed, but MediaMTX is missing.
    pause
    exit /b 0
)

echo.
echo Install completed successfully.
echo Next step: run scripts\windows\StartControl.bat
echo.
pause
exit /b 0