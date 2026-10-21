@echo off
cd /d "%~dp0"
start "" /b pythonw monitor.py 2> data\error.log