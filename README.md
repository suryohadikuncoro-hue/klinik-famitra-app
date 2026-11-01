---
title: Klinik Fa-Mitra
emoji: 🏥
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# Klinik Fa-Mitra App

Aplikasi manajemen Klinik Fa-Mitra (klinik pratama + apotek, mitra BPJS Kesehatan).
Fokus: keuangan klinik yang rapi per unit layanan × sumber bayar, master pasien & nakes,
pendaftaran kunjungan, dan rekam medis dasar.

Stack: **FastAPI + PostgreSQL (psycopg v3) + frontend vanilla JS** (tanpa build step).

## Status modul

| Tahap | Modul | Status |
|-------|-------|--------|
| 1 | Keuangan (transaksi, tagihan, klaim BPJS, laba per unit, neraca, modal) | selesai |
| 2 | Master pasien + nakes | selesai |
| 3 | Pendaftaran kunjungan (no. antrian otomatis) + rekam medis dasar | selesai |
| 4 | Farmasi + kasir/billing | berikutnya |
| 5 | SATUSEHAT + klaim BPJS real | butuh izin resmi Kemenkes |

## Menjalankan di komputer sendiri

1. Pastikan `uv` terpasang dan PostgreSQL lokal hidup (container `klinik-famitra-db`, port 5433).
2. Set `DATABASE_URL` (lihat `.env.example`) atau pakai default lokal.
3. Jalankan `start.bat`, atau:

```
uv run uvicorn klinik_famitra_app.main:app --host 0.0.0.0 --port 8000
```

4. Buka `http://localhost:8000` (perangkat lain di LAN: `http://IP_KOMPUTER:8000`).

Login awal: **admin / admin123** — wajib diganti lewat menu profil setelah login pertama.

## Deploy online

Arsitektur: repo **privat** di GitHub, database PostgreSQL di **Supabase**, backend Python
sebagai container Docker di **Render** (Web Service biasa, bukan Blueprint).
HTTPS/DNS via Cloudflare bila domain sudah ada.

### 1. Supabase — siapkan database

1. Buat project (region terdekat, mis. **ap-south-1** atau **ap-southeast-1**).
2. Salin connection string **Session pooler** dari *Project Settings → Database → Connection string*:

```
postgresql://postgres.<ref>:<PASSWORD>@aws-0-<region>.pooler.supabase.com:5432/postgres
```

> Pakai pooler, **bukan** `db.<ref>.supabase.co` — host itu IPv6-only dan tidak terjangkau
> dari banyak hosting.

Tidak perlu membuat tabel manual: `init_db()` + seed master data + akun admin berjalan
otomatis saat aplikasi start pertama kali.

### 2. Render — New Web Service (Docker)

Jangan pakai **New + → Blueprint** (jalur itu meminta kartu kredit). Pakai **Web Service**
biasa dan pilih runtime **Docker**; Render akan membaca `Dockerfile` di root repo.

1. Render Dashboard → **New +** → **Web Service** → hubungkan GitHub → pilih repo
   `klinik-famitra-app` (repo privat; beri Render akses ke repo itu bila diminta).
2. Isi form:
   - **Name**: `klinik-famitra-app` (menentukan URL `klinik-famitra-app.onrender.com`)
   - **Language / Runtime**: **Docker**
   - **Region**: **Singapore**
   - **Branch**: `master`
   - **Instance Type**: **Free**
3. **Environment Variables** → tambah satu:
   - Key: `DATABASE_URL`
   - Value: connection string Supabase di atas
4. **Advanced** (opsional tapi disarankan) → **Health Check Path**: `/api/health`
5. **Deploy Web Service** → tunggu build (Docker build ±3–5 menit) → buka
   `https://klinik-famitra-app.onrender.com`.

`render.yaml` di repo tetap ada, tapi **tidak dipakai** pada alur Web Service manual ini.

Catatan free tier Render: instance tidur setelah ±15 menit tanpa trafik, request pertama
setelah tidur butuh ±30–60 detik. 750 jam instance/bulan, 512 MB RAM. Data aman karena
tersimpan di Supabase, bukan di disk Render.

### Alternatif gratis tanpa kartu: Hugging Face Spaces

Bila Render tetap menolak akun tanpa kartu, repo ini juga siap untuk HF Spaces (Docker SDK):
`README.md` sudah ber-frontmatter `sdk: docker` + `app_port: 7860` dan `Dockerfile`
mendengarkan `$PORT` (default 7860). Langkahnya: New Space → SDK Docker → CPU basic (free) →
Settings → Variables and secrets → `DATABASE_URL` → `git push https://<user>:<HF_TOKEN>@huggingface.co/spaces/<user>/<space> master:main`.
Free tier: 2 vCPU / 16 GB RAM, tidur setelah ±48 jam tanpa kunjungan.

### 3. Cek kesehatan setelah deploy

```
curl https://<nama-service>.onrender.com/api/health
# {"ok":true,"db":"aws-0-ap-south-1.pooler.supabase.com:5432/postgres","pool":{...}}
```

`/api/health` membalas 200 bila app hidup **dan** database terjangkau, 503 bila koneksi DB
gagal (pesan error ikut dikembalikan). Isi `pool` menunjukkan koneksi yang tersedia/terpakai —
kalau `in_use` terus naik dan `available` 0, ada kebocoran koneksi.

### Performa & koneksi database

- Aplikasi memakai **connection pool** (`psycopg-pool`, 1–5 koneksi). Tanpa pool, setiap
  request membayar TCP + TLS + auth ke Supabase (±1,5–2 detik); dengan pool hanya satu
  round-trip query.
- `init_db()` mengirim seluruh DDL dalam **satu** pernyataan (satu round-trip, bukan satu
  per tabel) dan tetap idempotent, jadi tabel baru pada versi berikutnya ikut dibuat.
- Koneksi yang menganggur >5 menit dibuang dan koneksi mati dicek sebelum dipakai, supaya
  tidak ada request yang gagal setelah service tidur.

### Uji UI tanpa melihat layar

```
uv run --with websockets python scripts/ui-check.py http://127.0.0.1:8200
```

Login lewat API, set token di localStorage, buka dashboard, lalu cetak teks tiap tab
(Dashboard/Transaksi/Pendaftaran/Pasien) plus laporan error JS. Bisa diarahkan ke URL
Render setelah deploy.


### Update aplikasi

Setiap `git push` ke `master` otomatis memicu deploy ulang di Render.

## Keamanan & data

- `.env`, `data/`, `*.db` **tidak** masuk repo — data pasien dan keuangan tidak pernah
  ikut ter-commit.
- Password user di-hash PBKDF2-SHA256 (200k iterasi); sesi berupa token acak 32 byte,
  berlaku 7 hari, tersimpan di tabel `sessions`.
- Semua endpoint `/api/*` kecuali `/api/login` dan `/api/health` wajib header
  `Authorization: Bearer <token>`.

## Fitur per modul

### Keuangan
- **Dashboard**: kas tunai & saldo rekening (saldo berjalan, termasuk saldo awal), total masuk,
  total keluar, piutang BPJS, piutang pasien, laba akrual, rekap per metode bayar / unit
  layanan / sumber bayar / kategori, grafik arus kas 30 hari + donut komposisi pemasukan.
- **Transaksi**: pemasukan (unit layanan + sumber bayar) dan pengeluaran (kategori + unit
  opsional sebagai beban langsung), wajib pilih metode bayar (Tunai / Transfer / QRIS).
- **Tagihan**: satu kartu dengan mode **Tagihan Pasien** / **Klaim BPJS**. Tagihan pasien
  mendukung bayar bertahap dan split metode; klaim BPJS diajukan → cair.
- **Laporan**: Per Unit (pendapatan, beban langsung, beban bersama teralokasi, laba, margin),
  Neraca (aset = ekuitas), Modal (saldo awal, setoran, prive).
- **Master data**: unit layanan, sumber bayar, kategori pengeluaran, metode bayar.

### Pasien & nakes
- Pasien: no. RM otomatis (`RM-000001`), nama, NIK, no. BPJS, tanggal lahir, jenis kelamin,
  alamat, telepon. Pencarian live berdasarkan nama / RM / NIK / BPJS.
- Nakes: nama, profesi, SIP, status aktif/nonaktif.

### Pendaftaran & rekam medis
- Pendaftaran kunjungan dengan **no. antrian otomatis per tanggal** (`001`, `002`, …), pilih
  pasien, unit layanan, sumber bayar, dan nakes.
- Status kunjungan: menunggu → diperiksa → selesai (atau batal).
- Rekam medis per kunjungan: anamnesa, diagnosa, tindakan, terapi, keterangan.

## Aturan hitung yang penting

- **Dua sumbu terpisah**: `sumber_bayar` = siapa yang menanggung (BPJS/umum/asuransi);
  `metode_bayar` = instrumen uang masuk (Tunai/Transfer/QRIS). Pasien umum yang bayar QRIS
  tetap bersumber "Tunai/Umum".
- **Laba** = pendapatan − beban. Modal **bukan** pendapatan, prive **bukan** beban.
- **Neraca**: Aset (kas + rekening + piutang BPJS + piutang pasien) = Ekuitas (modal + laba
  berjalan).
- **Laba per unit**: beban bersama (pengeluaran tanpa unit) dialokasikan menurut proporsi
  pendapatan tiap unit; total laba semua unit = laba keseluruhan.
- **Klaim BPJS** adalah piutang: yang diajukan tapi belum cair belum jadi kas.

## Struktur proyek

```
klinik famitra app/
├── Dockerfile              (image produksi: python 3.14-slim + uv)
├── render.yaml             (blueprint Render)
├── start.bat               (jalankan lokal)
├── pyproject.toml / uv.lock
├── scripts/                (migrasi & uji)
└── src/klinik_famitra_app/
    ├── main.py             (API + routing + auth middleware)
    ├── database.py         (koneksi & skema PostgreSQL)
    ├── auth.py             (PBKDF2 + sesi token)
    ├── seed.py             (master data awal + admin)
    └── static/             (index.html, style.css, app.js, logo)
```

## Batasan saat ini

- Belum ada pencatatan utang usaha (pengeluaran dianggap langsung dibayar).
- Belum ada modul farmasi/kasir — masuk Tahap 4.
- Integrasi SATUSEHAT & klaim BPJS elektronik menunggu izin/kredensial resmi Kemenkes.
