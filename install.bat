@echo off
cd /d "%~dp0"
python -m venv .venv
if errorlevel 1 (echo Python 3.10-3.12 required.& pause & exit /b 1)
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements-train.txt
if errorlevel 1 (echo Installation failed.& pause & exit /b 1)
echo Dependencies installed. SpoofCeleb model must be trained separately. Read README.md.
echo FFmpeg must be installed and available on PATH.
pause
