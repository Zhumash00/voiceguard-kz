@echo off
cd /d "%~dp0"
python -m venv .venv
if errorlevel 1 (
 echo Python 3.10+ is required.
 pause
 exit /b 1
)
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
 echo Cannot install Python dependencies.
 pause
 exit /b 1
)
.venv\Scripts\python.exe scripts\download_model.py
if errorlevel 1 (
 echo Model download failed. Retry: .venv\Scripts\python.exe scripts\download_model.py
)
echo Install FFmpeg separately and ensure ffmpeg.exe is on PATH.
pause
