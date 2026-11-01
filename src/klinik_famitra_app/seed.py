"""Isi awal master data (unit layanan, sumber bayar, kategori, metode bayar)."""
from . import database as db

UNITS = [
    "IGD",
    "Rawat Jalan",
    "Rawat Inap",
    "Laboratorium",
    "Farmasi",
    "Ruang Laktasi",
    "Poli Gigi",
    "Lain-lain",
]

SUMBER = [
    "Tunai / Umum",
    "BPJS Kesehatan",
    "Asuransi",
    "Lain-lain",
]

KATEGORI = [
    "Gaji & Honor",
    "Obat & Bahan Habis Pakai",
    "Operasional (listrik/air/internet)",
    "Sewa, Aset & Alat",
    "ATK & Administrasi",
    "Lain-lain",
]

# (nama, jenis_dana, urutan). jenis_dana: 'kas' = uang tunai, 'bank' = rekening.
METODE = [
    ("Tunai", "kas", 1),
    ("Transfer", "bank", 2),
    ("QRIS", "bank", 3),
]


def seed():
    conn = db.get_conn()
    for table, items in (
        ("unit_layanan", UNITS),
        ("sumber_bayar", SUMBER),
        ("kategori_keluar", KATEGORI),
    ):
        count = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()["count"]
        if count == 0:
            for name in items:
                conn.execute(f"INSERT INTO {table} (nama) VALUES (%s)", (name,))

    count = conn.execute("SELECT COUNT(*) AS count FROM metode_bayar").fetchone()["count"]
    if count == 0:
        for nama, jenis, urut in METODE:
            conn.execute(
                "INSERT INTO metode_bayar (nama, jenis_dana, urutan) VALUES (%s,%s,%s)",
                (nama, jenis, urut),
            )
    conn.commit()
    conn.close()


def seed_admin():
    """Buat admin awal hanya bila tabel users kosong. Password awal harus segera diganti."""
    from . import auth

    conn = db.get_conn()
    count = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
    if count == 0:
        conn.execute(
            "INSERT INTO users (username, password_hash, nama, role) VALUES (%s,%s,%s,%s)",
            ("admin", auth.hash_password("admin123"), "Administrator", "admin"),
        )
        conn.commit()
    conn.close()
