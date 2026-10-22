@echo off
setlocal EnableDelayedExpansion
title AQI Forecasting Lab
cd /d "%~dp0"

REM ---- find Python 3.11+ ----
set "PY="
where py >nul 2>nul && (py -3 -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>nul && set "PY=py -3")
if not defined PY (
  where python >nul 2>nul && (python -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>nul && set "PY=python")
)
if not defined PY (
  echo.
  echo  Python 3.11 or newer is required.
  echo  Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH",
  echo  then double-click run.bat again.
  echo.
  pause
  exit /b 1
)

REM ---- pick a venv location ----
REM statsmodels ships DLLs with long paths. Deeply nested folders can hit the Windows
REM 260-character limit, so in that case the environment goes under %LOCALAPPDATA%.
set "HERE=%~dp0"
set /a LEN=0
for /l %%i in (0,1,260) do if not "!HERE:~%%i,1!"=="" set /a LEN=%%i+1
if !LEN! GTR 90 (
  set "VENV=%LOCALAPPDATA%\aqi-forecasting-lab\venv"
) else (
  set "VENV=%~dp0.venv"
)

if not exist "!VENV!\Scripts\python.exe" (
  echo Creating virtual environment in !VENV! ...
  %PY% -m venv "!VENV!" || (echo Could not create the virtual environment. & pause & exit /b 1)
)

REM ---- install dependencies once (reinstall only when requirements.txt changes) ----
set "STAMP=!VENV!\.requirements.txt"
fc /b requirements.txt "!STAMP!" >nul 2>nul
if errorlevel 1 (
  echo Installing dependencies, this takes a minute the first time ...
  "!VENV!\Scripts\python.exe" -m pip install --disable-pip-version-check -q --upgrade pip
  "!VENV!\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt || (echo Dependency install failed. & pause & exit /b 1)
  copy /y requirements.txt "!STAMP!" >nul
)

"!VENV!\Scripts\python.exe" serve.py
if errorlevel 1 pause
