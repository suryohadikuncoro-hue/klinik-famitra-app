"""Cek koneksi database (lokal atau Supabase) tanpa membocorkan kredensial.

Pakai:
    uv run python scripts/cek_db.py

DATABASE_URL dibaca dari env, atau dari file .env di root proyek.
Cetak: target (host:port/db), versi server, daftar tabel + jumlah baris,
dan status akun admin. Tidak pernah mencetak password.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def load_env_file() -> None:
    """Isi os.environ dari .env (kalau ada) tanpa menimpa env yang sudah di-set."""
    import os

    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> int:
    load_env_file()

    import psycopg  # noqa: PLC0415 - setelah env terisi

    from klinik_famitra_app import database as db  # noqa: PLC0415

    print(f"Target : {db.safe_target()}")
    try:
        conn = db.get_conn()
    except Exception as exc:  # noqa: BLE001
        print(f"GAGAL  : {exc}")
        print()
        print("Periksa: password benar? karakter khusus (@ : / ? # % &) sudah")
        print("di-percent-encode? host memakai pooler (bukan db.<ref>.supabase.co)?")
        return 1

    try:
        with conn.cursor() as cur:
            cur.execute("SELECT version() AS v")
            print(f"Server : {cur.fetchone()['v'].split(',')[0]}")

            cur.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
                """
            )
            tables = [r["table_name"] for r in cur.fetchall()]
            print(f"Tabel  : {len(tables)}")
            for name in tables:
                cur.execute(f'SELECT COUNT(*) AS c FROM "{name}"')
                print(f"  - {name:<16} {cur.fetchone()['c']:>6} baris")

            if "users" in tables:
                cur.execute("SELECT COUNT(*) AS c FROM users WHERE role='admin'")
                print(f"Admin  : {cur.fetchone()['c']} akun")
    finally:
        conn.close()

    print()
    print("OK — aplikasi siap dijalankan dengan database ini.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
