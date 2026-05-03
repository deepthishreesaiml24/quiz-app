@echo off
title Quiz Master Setup
color 0A

echo.
echo ==========================================
echo     QUIZ MASTER — SETUP AND RUN
echo ==========================================
echo.

:: Check Python
python --version > nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed!
    echo Please download Python from https://python.org
    pause
    exit /b
)

echo [1/3] Python found! Installing dependencies...
pip install Flask reportlab --quiet

echo [2/3] Starting Quiz Master App...
echo.
echo  URL    : http://127.0.0.1:5000
echo  Admin  : username=admin   password=admin123
echo  Student: username=student1  password=student123
echo.
echo ==========================================
echo Press Ctrl+C to stop the server
echo ==========================================
echo.

python app.py

pause
