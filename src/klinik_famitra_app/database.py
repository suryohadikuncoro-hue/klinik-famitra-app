"""Koneksi dan skema database PostgreSQL untuk Klinik Fa-Mitra.

Fase 1 migrasi: SQLite -> PostgreSQL (Supabase). Driver: psycopg (v3).
URL koneksi diambil dari env DATABASE_URL; default menunjuk ke
PostgreSQL lokal untuk pengembangan.
"""
import os

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

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


def safe_target() -> str:
    """Ringkasan target DB tanpa kredensial (aman untuk log/health check)."""
    from urllib.parse import urlsplit

    parts = urlsplit(DATABASE_URL)
    host = parts.hostname or "?"
    port = parts.port or 5432
    return f"{host}:{port}{parts.path or ''}"


_pool = None


def _conn_kwargs() -> dict:
    """Opsi koneksi: baris hasil = dict.

    Supabase: paksa SSL + nonaktifkan server-side prepared statement
    (pooler Supabase/PgBouncer tidak mendukung prepared statement, dan
    mewajibkan SSL). PostgreSQL lokal tidak terpengaruh.
    """
    kwargs = {"row_factory": dict_row, "prepare_threshold": None}
    if "supabase" in DATABASE_URL:
        kwargs["sslmode"] = "require"
    return kwargs


def get_pool():
    """Connection pool yang dibuka sekali per proses.

    Tanpa pool, tiap request membayar TCP + TLS + auth ke Supabase
    (~1,5-2 detik dari jaringan biasa). Dengan pool, koneksi dipakai ulang
    sehingga request hanya membayar satu round-trip query.
    """
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            DATABASE_URL,
            kwargs=_conn_kwargs(),
            min_size=1,
            max_size=5,
            open=False,
            close_returns=True,  # conn.close() -> kembali ke pool, bukan ditutup
            check=ConnectionPool.check_connection,  # buang koneksi yang sudah mati
            timeout=30,
            max_idle=300,  # koneksi menganggur >5 menit dibuang
            max_lifetime=1800,
            reconnect_timeout=120,
        )
        _pool.open(wait=True, timeout=30)
    return _pool


def get_conn():
    """Ambil koneksi dari pool. Tetap panggil conn.close() setelahnya.

    close() mengembalikan koneksi ke pool (close_returns=True), jadi pola
    `conn = get_conn() ... conn.close()` di seluruh kode tetap berlaku.
    """
    return get_pool().getconn()


def close_pool():
    """Tutup pool saat aplikasi berhenti."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def pool_stats() -> dict:
    """Ringkasan isi pool untuk diagnosis (dipakai /api/health)."""
    if _pool is None:
        return {}
    stats = _pool.get_stats()
    size = stats.get("pool_size", 0)
    available = stats.get("pool_available", 0)
    return {
        "size": size,
        "available": available,
        "in_use": size - available,
        "waiting": stats.get("requests_waiting", 0),
        "requests": stats.get("requests_num", 0),
        "errors": stats.get("requests_errors", 0),
    }



def init_db():
    """Buat skema bila belum ada.

    Semua DDL dikirim dalam SATU pernyataan: PostgreSQL mengeksekusinya
    berurutan dalam satu transaksi, jadi init hanya butuh satu round-trip
    (~0,3 s ke Supabase) bukan satu round-trip per tabel (~8 s).
    CREATE ... IF NOT EXISTS tetap idempotent, sehingga tabel baru pada
    versi aplikasi berikutnya ikut dibuat saat start.
    """
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(";\n".join(SCHEMA))
        conn.commit()
    finally:
        conn.close()
    print(f"[db] skema siap di {safe_target()}", flush=True)
