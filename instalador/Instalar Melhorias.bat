@echo off
rem Abre o instalador com janela (PowerShell ja vem no Windows 10/11).
start "" powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -WindowStyle Hidden -File "%~dp0arquivos\instalador.ps1"
