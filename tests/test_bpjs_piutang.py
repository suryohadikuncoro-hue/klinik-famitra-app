"""Uji logika BPJS: pemasukan bersumber BPJS = piutang, bukan kas.

Alur yang diuji:
  Transaksi (masuk, sumber BPJS)  -> baris klaim_bpjs status 'diajukan'
  Klaim BPJS "Terima Dana"        -> transaksi kas + status 'cair' (atomik)
  Laporan                         -> pendapatan tidak dihitung dua kali

Jalankan:  uv run --with pytest --with httpx pytest tests/test_bpjs_piutang.py -v
DB yang dipakai = DATABASE_URL (default PostgreSQL lokal container port 5433).
Data uji dihapus sendiri lewat ID yang dibuat; tidak ada "bersihkan semua".
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from klinik_famitra_app import database as db
from klinik_famitra_app.main import app

TODAY = date.today().isoformat()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        r = c.post("/api/login", json={"username": "admin", "password": "admin123"})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": "Bearer " + r.json()["token"]})
        yield c


@pytest.fixture(scope="module")
def master(client):
    r = client.get("/api/master")
    assert r.status_code == 200, r.text
    return r.json()


def _bpjs(master):
    rows = [s for s in master["sumber_bayar"] if s.get("is_bpjs")]
    assert len(rows) == 1, f"harus tepat satu sumber BPJS, dapat: {rows}"
    return rows[0]


def _bukan_bpjs(master):
    rows = [s for s in master["sumber_bayar"] if not s.get("is_bpjs")]
    assert rows, "butuh minimal satu sumber bayar non-BPJS"
    return rows[0]


def _unit(master):
    return master["unit_layanan"][0]


def _metode(master):
    return master["metode_bayar"][0]


def _laporan(client):
    r = client.get(f"/api/laporan?dari={TODAY}&sampai={TODAY}")
    assert r.status_code == 200, r.text
    return r.json()


def _bersihkan(klaim_ids=(), transaksi_ids=()):
    """Hapus HANYA baris yang dibuat uji ini.

    Urutan wajib: lepas tautan klaim -> transaksi -> klaim, karena
    klaim_bpjs.transaksi_id punya FK ke transaksi.
    """
    conn = db.get_conn()
    for kid in klaim_ids:
        conn.execute("UPDATE klaim_bpjs SET transaksi_id=NULL WHERE id=%s", (kid,))
    for tid in transaksi_ids:
        conn.execute("DELETE FROM transaksi WHERE id=%s", (tid,))
    for kid in klaim_ids:
        conn.execute("DELETE FROM klaim_bpjs WHERE id=%s", (kid,))
    conn.commit()
    conn.close()


def test_pemasukan_bpjs_menjadi_piutang_lalu_diterima_tanpa_hitung_ganda(client, master):
    bpjs, unit, metode = _bpjs(master), _unit(master), _metode(master)
    jumlah = 750_000
    tanda = "uji-bpjs-" + uuid.uuid4().hex[:8]
    klaim_id = transaksi_id = None

    sebelum = _laporan(client)
    try:
        # 1) Pemasukan bersumber BPJS -> piutang, TIDAK menambah kas
        r = client.post("/api/transaksi", json={
            "tanggal": TODAY,
            "jenis": "masuk",
            "unit_layanan_id": unit["id"],
            "sumber_bayar_id": bpjs["id"],
            "jumlah": jumlah,
            "keterangan": tanda,
            "dicatat_oleh": "uji",
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["pencatatan"] == "piutang_bpjs", body
        klaim_id = body["klaim_id"]
        assert klaim_id and body["id"] == klaim_id

        # Metode bayar tidak wajib untuk BPJS (uangnya belum masuk)
        sesudah = _laporan(client)
        assert sesudah["masuk"] == sebelum["masuk"], "pemasukan BPJS tidak boleh jadi kas"
        assert sesudah["bpjs_periode"] - sebelum["bpjs_periode"] == jumlah
        assert sesudah["piutang_bpjs"] - sebelum["piutang_bpjs"] == jumlah
        assert sesudah["pendapatan_akrual"] - sebelum["pendapatan_akrual"] == jumlah

        # 2) Klaim muncul otomatis di daftar, belum ada input manual
        daftar = client.get("/api/klaim").json()
        baris = [k for k in daftar if k["id"] == klaim_id]
        assert baris, "klaim harus terbentuk otomatis dari transaksi"
        assert baris[0]["status"] == "diajukan"
        assert baris[0]["jumlah"] == jumlah
        assert baris[0]["sumber"] == bpjs["nama"]

        # 3) Input manual klaim ditolak
        r = client.post("/api/klaim", json={"tanggal_ajuan": TODAY, "jumlah": 1000})
        assert r.status_code == 400
        assert "otomatis" in r.json()["detail"].lower()

        # 4) Terima dana wajib menyebut metode + tanggal
        assert client.post(f"/api/klaim/{klaim_id}/cair", json={"tanggal_cair": TODAY}).status_code == 400
        assert client.post(
            f"/api/klaim/{klaim_id}/cair", json={"tanggal_cair": TODAY, "metode_bayar_id": 999999}
        ).status_code == 400
        assert client.post(
            f"/api/klaim/{klaim_id}/cair",
            json={"tanggal_cair": "2000-01-01", "metode_bayar_id": metode["id"]},
        ).status_code == 400, "tanggal terima dana tidak boleh sebelum pengakuan"

        # 5) Terima dana: piutang -> kas, satu langkah
        r = client.post(
            f"/api/klaim/{klaim_id}/cair",
            json={"tanggal_cair": TODAY, "metode_bayar_id": metode["id"]},
        )
        assert r.status_code == 200, r.text
        transaksi_id = r.json()["transaksi_id"]
        assert transaksi_id

        sesudah_cair = _laporan(client)
        assert sesudah_cair["masuk"] - sebelum["masuk"] == jumlah, "dana masuk ke kas"
        assert sesudah_cair["masuk_klaim_bpjs"] - sebelum["masuk_klaim_bpjs"] == jumlah
        assert sesudah_cair["piutang_bpjs"] == sebelum["piutang_bpjs"], "piutang berkurang"
        # INTI: pendapatan tidak boleh naik lagi saat dana diterima
        assert sesudah_cair["pendapatan_akrual"] == sesudah["pendapatan_akrual"]
        assert sesudah_cair["laba_akrual"] == sesudah["laba_akrual"]

        # 6) Klik ganda tidak membuat pemasukan kedua
        r = client.post(
            f"/api/klaim/{klaim_id}/cair",
            json={"tanggal_cair": TODAY, "metode_bayar_id": metode["id"]},
        )
        assert r.status_code == 200
        assert r.json().get("sudah_cair") is True
        assert r.json()["transaksi_id"] == transaksi_id
        assert _laporan(client)["masuk"] == sesudah_cair["masuk"]

        # 7) Jejak tidak boleh hilang: klaim & transaksi penerimaan terkunci
        assert client.delete(f"/api/klaim/{klaim_id}").status_code == 400
        assert client.delete(f"/api/transaksi/{transaksi_id}").status_code == 400

        # 8) Invariant laporan per unit tetap sejalan dengan laba akrual
        pu = client.get(f"/api/laporan-unit?dari={TODAY}&sampai={TODAY}").json()
        assert sum(u["laba"] for u in pu["units"]) == pu["total"]["laba"]
        assert pu["total"]["laba"] == _laporan(client)["laba_akrual"]
    finally:
        _bersihkan([klaim_id] if klaim_id else [], [transaksi_id] if transaksi_id else [])


def test_tagihan_dengan_sumber_bpjs_ditolak_agar_piutang_tidak_ganda(client, master):
    r = client.post("/api/tagihan", json={
        "tanggal": TODAY,
        "nama_pasien": "uji",
        "unit_layanan_id": _unit(master)["id"],
        "sumber_bayar_id": _bpjs(master)["id"],
        "total": 50_000,
    })
    assert r.status_code == 400
    assert "klaim" in r.json()["detail"].lower()


def test_pemasukan_non_bpjs_tetap_jadi_kas(client, master):
    sumber, unit, metode = _bukan_bpjs(master), _unit(master), _metode(master)
    jumlah = 125_000
    tid = None
    sebelum = _laporan(client)
    try:
        r = client.post("/api/transaksi", json={
            "tanggal": TODAY,
            "jenis": "masuk",
            "unit_layanan_id": unit["id"],
            "sumber_bayar_id": sumber["id"],
            "metode_bayar_id": metode["id"],
            "jumlah": jumlah,
        })
        assert r.status_code == 200, r.text
        assert r.json().get("pencatatan") is None
        tid = r.json()["id"]
        sesudah = _laporan(client)
        assert sesudah["masuk"] - sebelum["masuk"] == jumlah
        assert sesudah["bpjs_periode"] == sebelum["bpjs_periode"]
    finally:
        _bersihkan([], [tid] if tid else [])
