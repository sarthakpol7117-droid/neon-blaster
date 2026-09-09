@echo off
cd /d "%~dp0"
python neon_blaster.py
if errorlevel 1 pause
