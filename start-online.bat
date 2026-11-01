@echo off
REM ============================================================
REM  Jalankan Klinik Fa-Mitra App + akses online (Cloudflare Tunnel)
REM  Gratis, tanpa kartu kredit, tanpa akun Cloudflare.
REM
REM  Cara pakai: klik dua kali file ini.
REM  Jendela pertama = server aplikasi, jendela kedua = tunnel.
REM  URL publik muncul di jendela tunnel (baris "trycloudflare.com").
REM
REM  CATATAN PENTING:
REM  - Komputer ini harus tetap HIDUP selama aplikasi dipakai online.
REM  - URL trycloudflare.com BERGANTI setiap file ini dijalankan ulang.
REM  - Akses dilindungi Cloudflare Access: hanya email di bawah yang
REM    bisa masuk (dapat PIN sekali pakai lewat email).
REM ============================================================

set EMAIL=suryohadikuncoro@gmail.com
set CLOUDFLARED="C:\Program Files (x86)\cloudflared\cloudflared.exe"

cd /d "%~dp0"

REM 1) Server aplikasi (pakai DATABASE_URL dari file .env)
start "Klinik Fa-Mitra - Server" cmd /k "uv run uvicorn klinik_famitra_app.main:app --host 127.0.0.1 --port 8000"

REM beri waktu server siap
timeout /t 12 /nobreak >nul

REM 2) Tunnel ke internet
start "Klinik Fa-Mitra - Tunnel" cmd /k "%CLOUDFLARED% tunnel --url http://localhost:8000 --allowed-mail %EMAIL% --no-autoupdate"

echo.
echo Dua jendela sudah dibuka.
echo  - Jendela "Server"  : aplikasi berjalan di http://localhost:8000
echo  - Jendela "Tunnel"  : cari baris https://....trycloudflare.com  ^<-- itu URL online-nya
echo.
echo Bagikan URL itu ke petugas. Mereka akan diminta memasukkan email %EMAIL%
echo lalu PIN yang dikirim ke email tersebut.
echo.
pause
