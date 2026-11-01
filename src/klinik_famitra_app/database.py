"""Koneksi dan skema database PostgreSQL untuk Klinik Fa-Mitra.

Fase 1 migrasi: SQLite -> PostgreSQL (Supabase). Driver: psycopg (v3).
URL koneksi diambil dari env DATABASE_URL; default menunjuk ke
PostgreSQL lokal untuk pengembangan.
"""
import os

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://klinik_admin:klinik_dev_password@127.0.0.1:5433/klinik_famitra",
)

# Daftar pernyataan DDL, dieksekusi berurutan saat init_db.
SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS unit_layanan (
        id SERIAL PRIMARY KEY,
        nama TEXT NOT NULL UNIQUE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sumber_bayar (
        id SERIAL PRIMARY KEY,
        nama TEXT NOT NULL UNIQUE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS kategori_keluar (
        id SERIAL PRIMARY KEY,
        nama TEXT NOT NULL UNIQUE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS metode_bayar (
        id SERIAL PRIMARY KEY,
        nama TEXT NOT NULL UNIQUE,
        jenis_dana TEXT NOT NULL CHECK (jenis_dana IN ('kas', 'bank')),
        urutan INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tagihan (
        id SERIAL PRIMARY KEY,
        tanggal TEXT NOT NULL,
        nama_pasien TEXT,
        unit_layanan_id INTEGER REFERENCES unit_layanan(id),
        sumber_bayar_id INTEGER REFERENCES sumber_bayar(id),
        total INTEGER NOT NULL CHECK (total > 0),
        keterangan TEXT,
        created_at TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS')
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS transaksi (
        id SERIAL PRIMARY KEY,
        tanggal TEXT NOT NULL,
        jenis TEXT NOT NULL CHECK (jenis IN ('masuk', 'keluar')),
        unit_layanan_id INTEGER REFERENCES unit_layanan(id),
        sumber_bayar_id INTEGER REFERENCES sumber_bayar(id),
        kategori_keluar_id INTEGER REFERENCES kategori_keluar(id),
        metode_bayar_id INTEGER REFERENCES metode_bayar(id),
        tagihan_id INTEGER REFERENCES tagihan(id),
        jumlah INTEGER NOT NULL,
        keterangan TEXT,
        dicatat_oleh TEXT,
        created_at TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS')
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS klaim_bpjs (
        id SERIAL PRIMARY KEY,
        tanggal_ajuan TEXT NOT NULL,
        unit_layanan_id INTEGER REFERENCES unit_layanan(id),
        jumlah INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'diajukan' CHECK (status IN ('diajukan', 'cair')),
        tanggal_cair TEXT,
        keterangan TEXT,
        created_at TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS')
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS modal (
        id SERIAL PRIMARY KEY,
        tanggal TEXT NOT NULL,
        jenis TEXT NOT NULL CHECK (jenis IN ('saldo_awal', 'setoran', 'prive')),
        jenis_dana TEXT NOT NULL CHECK (jenis_dana IN ('kas', 'bank')),
        jumlah INTEGER NOT NULL CHECK (jumlah > 0),
        keterangan TEXT,
        created_at TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS')
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pasien (
        id SERIAL PRIMARY KEY,
        no_rm TEXT UNIQUE,
        nama TEXT NOT NULL,
        nik TEXT,
        no_bpjs TEXT,
        tanggal_lahir TEXT,
        jenis_kelamin TEXT CHECK (jenis_kelamin IN ('L', 'P')),
        alamat TEXT,
        no_telepon TEXT,
        created_at TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS')
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS nakes (
        id SERIAL PRIMARY KEY,
        nama TEXT NOT NULL,
        profesi TEXT,
        sip TEXT,
        status TEXT NOT NULL DEFAULT 'aktif' CHECK (status IN ('aktif', 'nonaktif')),
        created_at TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS')
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        nama TEXT,
        role TEXT NOT NULL DEFAULT 'petugas' CHECK (role IN ('admin', 'petugas')),
        created_at TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS')
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id),
        expires_at BIGINT NOT NULL,
        created_at TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS')
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS kunjungan (
        id SERIAL PRIMARY KEY,
        tanggal TEXT NOT NULL,
        no_antrian TEXT,
        pasien_id INTEGER NOT NULL REFERENCES pasien(id),
        unit_layanan_id INTEGER REFERENCES unit_layanan(id),
        nakes_id INTEGER REFERENCES nakes(id),
        sumber_bayar_id INTEGER REFERENCES sumber_bayar(id),
        keluhan TEXT,
        status TEXT NOT NULL DEFAULT 'menunggu' CHECK (status IN ('menunggu', 'diperiksa', 'selesai', 'batal')),
        created_at TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS')
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rekam_medis (
        id SERIAL PRIMARY KEY,
        kunjungan_id INTEGER NOT NULL UNIQUE REFERENCES kunjungan(id),
        anamnesa TEXT,
        diagnosa TEXT,
        tindakan TEXT,
        terapi TEXT,
        keterangan TEXT,
        created_at TEXT NOT NULL DEFAULT to_char(NOW(), 'YYYY-MM-DD HH24:MI:SS')
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_kunjungan_tanggal ON kunjungan (tanggal)",
    "CREATE INDEX IF NOT EXISTS idx_modal_tanggal ON modal (tanggal)",
    "CREATE INDEX IF NOT EXISTS idx_transaksi_tagihan ON transaksi (tagihan_id)",
    "CREATE INDEX IF NOT EXISTS idx_transaksi_metode ON transaksi (metode_bayar_id)",
]


def get_conn():
    """Buka koneksi psycopg baru (baris hasil = dict). Panggil conn.close() setelahnya."""
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_db():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            for stmt in SCHEMA:
                cur.execute(stmt)
        conn.commit()
    finally:
        conn.close()
