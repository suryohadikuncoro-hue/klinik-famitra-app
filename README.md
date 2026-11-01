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

## Deploy online (GitHub + Supabase + Render)

Arsitektur: repo **privat** di GitHub, database PostgreSQL di **Supabase**, backend Python
di **Render** (Docker, free tier), HTTPS/DNS via Cloudflare bila domain sudah ada.

### 1. Supabase — siapkan database

1. Buat project (region **ap-southeast-1** / Singapore supaya dekat).
2. Salin connection string **Session pooler** dari *Project Settings → Database → Connection string*:

```
postgresql://postgres.<ref>:<PASSWORD>@aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres
```

> Pakai pooler, **bukan** `db.<ref>.supabase.co` — host itu IPv6-only dan tidak terjangkau
> dari Render free tier. Session pooler (port 5432) dipakai karena app membuka koneksi baru
> per request tanpa prepared statement server-side.

Tidak perlu membuat tabel manual: `init_db()` + seed master data + akun admin berjalan
otomatis saat aplikasi start pertama kali.

### 2. Render — deploy backend

1. Render Dashboard → **New +** → **Blueprint** → hubungkan akun GitHub → pilih repo
   `klinik-famitra-app` (repo privat, beri Render akses ke repo itu).
2. Render membaca `render.yaml` dan membuat service `klinik-famitra-app` (Docker, plan free).
3. Saat diminta, isi env var **`DATABASE_URL`** dengan connection string Supabase di atas.
4. **Apply** → tunggu build selesai → buka `https://klinik-famitra-app.onrender.com`.

Catatan free tier Render: instance tidur setelah ±15 menit tanpa trafik, request pertama
setelah tidur butuh ±30–60 detik untuk bangun. Untuk klinik yang aktif di jam kerja ini
biasanya tidak terasa.

### 3. Cek kesehatan setelah deploy

```
curl https://<nama-service>.onrender.com/api/health
# {"ok":true,"db":"aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres"}
```

`/api/health` dipakai Render sebagai health check: 200 bila app hidup **dan** database
terjangkau, 503 bila koneksi DB gagal (pesan error ikut dikembalikan).

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
