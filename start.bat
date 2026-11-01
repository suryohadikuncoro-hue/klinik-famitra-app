@echo off
cd /d "%~dp0"
echo ============================================
echo  Klinik Fa-Mitra App - Modul Keuangan
echo  Buka browser: http://localhost:8000
echo  (Jaringan lokal: http://IP_KOMPUTER_INI:8000)
echo  Tekan Ctrl+C untuk berhenti.
echo ============================================
uv run uvicorn klinik_famitra_app.main:app --host 0.0.0.0 --port 8000
pause
