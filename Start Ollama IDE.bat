@echo off
setlocal
title Ollama Agentic IDE v1.1
cd /d "%~dp0"

:: Check for Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.8+ from python.org
    pause
    exit /b
)

:: Check if Ollama is running
tasklist /fi "imagename eq ollama.exe" | find /i "ollama.exe" > nul
if %errorlevel% neq 0 (
    echo [NOTICE] Ollama service not detected. 
    echo AI features may not work until you start Ollama.
    echo.
)

echo ==========================================
echo    Ollama Agentic IDE v1.1 Starter
echo ==========================================
echo [*] Working Dir: %CD%
echo [*] Launching IDE...
echo.

:: Launch the app
:: Use 'start' to let the batch file finish if you want, 
:: but staying attached allows seeing console output (useful for IDEs).
python Ollama_Agentic_IDE_v1_1.py

if %errorlevel% neq 0 (
    echo.
    echo [!] The app closed unexpectedly (Exit Code: %errorlevel%).
    echo [?] Troubleshooting:
    echo     1. Check if dependencies are installed: pip install ollama schedule
    echo     2. Check if Ollama is running locally.
    pause
)
