# Klinik Fa-Mitra App — Modul Keuangan (Tahap 1)

Aplikasi pencatatan keuangan klinik. Fokus: kas masuk/keluar yang tercatat rapi, per unit layanan × sumber bayar, laba per unit, plus piutang klaim BPJS.

## Cara menjalankan

1. Pastikan `uv` sudah terpasang (sudah ada di mesin ini).
2. Klik dua kali `start.bat` (atau jalankan perintah di bawah di folder ini):

```
uv run uvicorn klinik_famitra_app.main:app --host 0.0.0.0 --port 8000
```

3. Buka browser:
   - Di komputer ini: `http://localhost:8000`
   - Dari HP / komputer lain (satu jaringan): `http://IP_KOMPUTER_INI:8000`
     - Cara lihat IP: buka CMD, ketik `ipconfig`, lihat baris "IPv4 Address".

4. Untuk berhenti: tekan `Ctrl+C`.

## Fitur (Tahap 1)

- **Dashboard**: **kas tunai** dan **saldo di rekening** (saldo berjalan, termasuk saldo awal), total masuk, total keluar, piutang BPJS, piutang pasien, laba (akrual), rekap per metode bayar / unit layanan / sumber bayar / kategori. Auto-refresh tiap 20 detik.
- **Transaksi**: catat pemasukan (unit layanan + sumber bayar) dan pengeluaran (kategori + **unit opsional** untuk beban langsung), wajib pilih **metode bayar** (Tunai / Transfer / QRIS).
- **Tagihan**: satu kartu dengan pilihan **Tagihan Pasien** / **Klaim BPJS** (pola sama seperti Pemasukan/Pengeluaran di Transaksi). Tagihan pasien mendukung pembayaran bertahap dan split metode; klaim BPJS diajukan → cair.
- **Laporan → Per Unit**: pendapatan (kas + piutang BPJS + piutang pasien), beban langsung, beban bersama teralokasi, laba, dan margin per unit layanan.
- **Laporan → Neraca**: aset (kas, rekening, piutang) vs ekuitas (modal + laba berjalan), dengan penanda seimbang/tidak.
- **Laporan → Modal**: catat **saldo awal** kas/rekening, **setoran modal**, dan **prive** (penarikan pemilik).
- **Master data**: kelola unit layanan, sumber bayar, kategori pengeluaran, dan metode bayar (tiap metode dipetakan ke kas tunai atau rekening) — bisa tambah, ubah, hapus.

## Tampilan

- **Desktop (≥1024px)**: sidebar kiri berisi brand + navigasi, konten lebar (maks. 1180px). Dashboard pakai 3 kolom KPI, kartu laba lebar, grafik arus kas 30 hari, dan donut komposisi pemasukan per unit.
- **HP/tablet**: navigasi bawah 5 tab, KPI 2 kolom, grafik menumpuk vertikal.
- Grafik digambar dengan **SVG murni** (tanpa CDN/library) — tetap jalan di jaringan lokal tanpa internet.

## Kas tunai vs rekening

- Tiap metode bayar punya jenis dana: **Tunai → kas**, **Transfer/QRIS → rekening**.
- Kas tunai = saldo awal kas + setoran modal ke kas − prive dari kas + uang masuk tunai − pengeluaran tunai.
- Saldo rekening = saldo awal rekening + setoran modal ke rekening − prive dari rekening + uang masuk transfer/QRIS − pengeluaran transfer/QRIS.
- Metode baru (mis. kartu debit, e-wallet) bisa ditambah di Master → Metode Bayar, lalu pilih jenis dananya.

## Laba & modal

- **Laba (laba rugi)** = pendapatan − beban. Modal **tidak** memengaruhi laba; modal muncul di **neraca**.
- **Neraca**: Aset (kas + rekening + piutang BPJS + piutang pasien) = Ekuitas (modal + laba berjalan).
- **Modal** = saldo awal + setoran modal − prive. Setoran modal bukan pendapatan; prive bukan beban.
- Tanpa saldo awal, kartu kas/rekening mulai dari Rp0 walaupun di laci/rekening sudah ada uang — isi dulu di Laporan → Modal.

## Cara pakai singkat

1. **Pertama kali**: buka Laporan → Modal, isi **Saldo Awal** kas tunai dan rekening sesuai uang yang benar-benar ada.
2. Pasien bayar tagihan → buat di tab "Tagihan" (isi total tagihan), lalu klik "Bayar" pada tagihan itu.
   - Bayar sebagian: masukkan jumlah yang dibayar saja; sisa tercatat otomatis.
   - Bayar campuran: proses dengan metode Tunai, lalu klik "Bayar" lagi untuk sisanya via Transfer/QRIS.
3. Pemasukan tanpa tagihan → "Transaksi" jenis Pemasukan, pilih unit + sumber + metode.
4. Pemasukan BPJS yang sudah cair → catat di "Transaksi" jenis Pemasukan, sumber "BPJS Kesehatan".
5. Klaim BPJS yang BARU diajukan (belum cair) → Tab "Tagihan" → "Klaim BPJS". Saat cair → klik "Cairkan".
6. Pengeluaran → "Transaksi" jenis Pengeluaran, pilih kategori + metode (tunai/transfer).
   - **Beban langsung unit** (mis. reagen untuk Laboratorium, obat untuk Farmasi): pilih unit.
   - **Beban bersama** (gaji, sewa, listrik, ATK): biarkan unit kosong → dialokasikan menurut proporsi pendapatan tiap unit.

## Laporan per unit

- Pendapatan per unit = uang masuk (kas) + klaim BPJS diajukan + sisa tagihan pasien, untuk unit itu.
- Beban langsung = pengeluaran yang ditandai ke unit tersebut.
- Beban bersama = pengeluaran tanpa unit, dibagi ke tiap unit **sesuai proporsi pendapatan**.
- Laba unit = pendapatan − beban langsung − beban bersama teralokasi. Total semua unit = laba keseluruhan.

## Struktur data

- Database SQLite tersimpan di folder `data/klinik.db` (terbuat otomatis saat pertama jalan).
- Master data awal sudah terisi (unit layanan, sumber bayar, kategori, metode bayar) — bisa ditambah/diubah lewat menu "Master".

## Catatan / batasan Tahap 1

- Belum ada login/autentikasi (jangkauan LAN lokal). Autentikasi + hosting online direncanakan di tahap berikutnya.
- Belum ada pencatatan utang usaha (pengeluaran dianggap langsung dibayar).
- Ini tahap pertama; modul berikutnya (master pasien, pendaftaran, rekam medis, farmasi) akan ditambahkan bertahap.

## Struktur proyek

```
klinik famitra app/
├── start.bat
├── pyproject.toml
├── data/klinik.db          (terbuat otomatis)
└── src/klinik_famitra_app/
    ├── main.py             (API + routing)
    ├── database.py         (skema SQLite)
    ├── seed.py             (master data awal)
    └── static/             (tampilan web)
        ├── index.html
        ├── style.css
        └── app.js
```
