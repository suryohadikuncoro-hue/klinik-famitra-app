"""Migrasi data SQLite (data/klinik.db) -> PostgreSQL (Fase 2).

Aman dijalankan berulang (idempotent): upsert ON CONFLICT (id) DO UPDATE,
lalu setval sequence ke id maksimum supaya id baru tidak bentrok.

Yang dimigrasi: transaksi, users (password_hash dipertahankan utuh).
Yang DILEWATI (sengaja):
- Master (unit/sumber/kategori/metode) — sudah identik via seed.py.
- sessions — sesi lama dibuang, semua login ulang.
- tagihan/klaim/modal/pasien/nakes — kosong di SQLite.

Jalankan:  uv run python scripts/migrate_sqlite_to_pg.py
"""
import os
import sqlite3

import psycopg
from psycopg.rows import dict_row

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQLITE_PATH = os.path.join(BASE, "data", "klinik.db")
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://klinik_admin:klinik_dev_password@127.0.0.1:5433/klinik_famitra",
)

# tabel -> kolom (tanpa id, id dimasukkan eksplisit). Nilai None juga ikut.
TABLES = {
    "transaksi": [
        "id", "tanggal", "jenis", "unit_layanan_id", "sumber_bayar_id",
        "kategori_keluar_id", "metode_bayar_id", "tagihan_id", "jumlah",
        "keterangan", "dicatat_oleh", "created_at",
    ],
    "users": ["id", "username", "password_hash", "nama", "role", "created_at"],
}


def main():
    if not os.path.exists(SQLITE_PATH):
        print("SQLite tidak ditemukan:", SQLITE_PATH)
        return

    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row

    pg = psycopg.connect(DATABASE_URL, row_factory=dict_row)

    for table, cols in TABLES.items():
        rows = [dict(r) for r in sqlite_conn.execute(f"SELECT * FROM {table}")]
        if not rows:
            print(f"{table}: 0 baris (lewati)")
            continue

        col_list = ", ".join(cols)
        placeholders = ", ".join(["%s"] * len(cols))
        update = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "id")
        sql = (
            f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
            f"ON CONFLICT (id) DO UPDATE SET {update}"
        )
        with pg.cursor() as cur:
            for r in rows:
                cur.execute(sql, tuple(r[c] for c in cols))
        pg.commit()

        max_id = max(r["id"] for r in rows)
        seq = f"{table}_id_seq"
        with pg.cursor() as cur:
            cur.execute(
                "SELECT setval(%s, GREATEST((SELECT COALESCE(MAX(id),0) FROM {}), %s))".format(table),
                (seq, max_id),
            )
        pg.commit()
        print(f"{table}: {len(rows)} baris dimigrasi, sequence {seq} -> {max_id}")

    sqlite_conn.close()
    pg.close()
    print("Selesai.")


if __name__ == "__main__":
    main()
