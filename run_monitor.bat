@echo off
cd /d "%~dp0"
start "" /b pythonw monitor.py 2> data\error.log
timeout /t 5 /nobreak > nul
start "" /b pythonw bot.py 2> data\bot_error.log