"""Uji alur tulis end-to-end (pasien -> kunjungan -> rekam medis -> tagihan ->
pembayaran bertahap -> klaim BPJS), lalu hapus HANYA data yang dibuat skrip ini.

Pakai:
    uv run python scripts/uji_alur.py [http://127.0.0.1:8200]
"""
import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8200"
TOKEN = ""
created = {"pasien": [], "kunjungan": [], "tagihan": [], "klaim": [], "transaksi": []}


def call(method, path, payload=None, expect=200):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if TOKEN:
        req.add_header("Authorization", "Bearer " + TOKEN)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            body = json.load(r)
            status = r.status
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        status = e.code
    ok = "OK " if status == expect else "GAGAL"
    print(f"  {ok} {method:6} {path:38} -> {status} {str(body)[:90]}")
    assert status == expect, f"{method} {path} harap {expect}, dapat {status}: {body}"
    return body


def main():
    global TOKEN
    print("== login ==")
    TOKEN = call("POST", "/api/login", {"username": "admin", "password": "admin123"})["token"]

    print("== master (id dibaca dari API, bukan ditebak) ==")
    m = call("GET", "/api/master")
    unit = {u["nama"]: u["id"] for u in m["unit_layanan"]}
    sumber = {s["nama"]: s["id"] for s in m["sumber_bayar"]}
    kategori = {k["nama"]: k["id"] for k in m["kategori_keluar"]}
    metode = {x["nama"]: x["id"] for x in m["metode_bayar"]}
    print(f"  unit={len(unit)} sumber={len(sumber)} kategori={len(kategori)} metode={len(metode)}")
    assert "Rawat Jalan" in unit and "BPJS Kesehatan" in sumber, "master data tidak lengkap"

    try:
        print("== pasien ==")
        p = call("POST", "/api/pasien", {
            "nama": "UJI ALUR (hapus)", "nik": "0000000000000001",
            "jenis_kelamin": "L", "no_telepon": "0812",
        })
        pid = p["id"]; created["pasien"].append(pid)
        row = [x for x in call("GET", "/api/pasien") if x["id"] == pid][0]
        print(f"  no_rm otomatis: {row['no_rm']}")
        assert row["no_rm"].startswith("RM-"), "no_rm tidak otomatis"

        print("== kunjungan ==")
        k = call("POST", "/api/kunjungan", {
            "tanggal": "2026-11-01", "pasien_id": pid,
            "unit_layanan_id": unit["Rawat Jalan"],
            "sumber_bayar_id": sumber["Tunai / Umum"],
            "keluhan": "demam",
        })
        kid = k["id"]; created["kunjungan"].append(kid)
        k2 = call("POST", "/api/kunjungan", {
            "tanggal": "2026-11-01", "pasien_id": pid,
            "unit_layanan_id": unit["Rawat Jalan"],
        })
        created["kunjungan"].append(k2["id"])
        daftar = call("GET", "/api/kunjungan?tanggal=2026-11-01")
        antrian = [x["no_antrian"] for x in daftar if x["id"] in (kid, k2["id"])]
        print(f"  no_antrian otomatis: {antrian}")
        assert all(a and len(a) == 3 for a in antrian), "no_antrian tidak 3 digit"

        print("== rekam medis (upsert 2x, isi bertahap) ==")
        call("POST", "/api/rekam-medis", {"kunjungan_id": kid, "anamnesa": "panas 3 hari"})
        call("POST", "/api/rekam-medis", {"kunjungan_id": kid, "diagnosa": "ISPA"})
        rm = call("GET", f"/api/rekam-medis/{kid}")
        print(f"  isi RM: anamnesa={rm.get('anamnesa')!r} diagnosa={rm.get('diagnosa')!r}")
        assert rm.get("anamnesa") == "panas 3 hari" and rm.get("diagnosa") == "ISPA", \
            "simpan bertahap menghapus field sebelumnya"
        call("POST", "/api/rekam-medis", {"kunjungan_id": kid, "terapi": "parasetamol"})
        call("POST", "/api/rekam-medis", {"kunjungan_id": kid, "terapi": ""})
        rm2 = call("GET", f"/api/rekam-medis/{kid}")
        print(f"  setelah terapi dikosongkan: terapi={rm2.get('terapi')!r} "
              f"anamnesa={rm2.get('anamnesa')!r}")
        assert rm2.get("terapi") == "" and rm2.get("anamnesa") == "panas 3 hari", \
            "pengosongan field harus jalan tanpa menghapus field lain"

        print("== tagihan + bayar bertahap + split metode ==")
        tg = call("POST", "/api/tagihan", {
            "tanggal": "2026-11-01", "nama_pasien": "UJI ALUR (hapus)",
            "unit_layanan_id": unit["Rawat Jalan"],
            "sumber_bayar_id": sumber["Tunai / Umum"], "total": 300000,
        })
        tid = tg["id"]; created["tagihan"].append(tid)
        b1 = call("POST", f"/api/tagihan/{tid}/bayar", {
            "tanggal": "2026-11-01", "jumlah": 100000, "metode_bayar_id": metode["Tunai"],
        })
        created["transaksi"].append(b1.get("id"))
        sisa1 = [x for x in call("GET", "/api/tagihan") if x["id"] == tid][0]["sisa"]
        print(f"  sisa setelah bayar 100.000: {sisa1}")
        b2 = call("POST", f"/api/tagihan/{tid}/bayar", {
            "tanggal": "2026-11-01", "jumlah": 200000, "metode_bayar_id": metode["Transfer"],
        })
        created["transaksi"].append(b2.get("id"))
        sisa2 = [x for x in call("GET", "/api/tagihan") if x["id"] == tid][0]["sisa"]
        print(f"  sisa setelah pelunasan: {sisa2}")
        assert sisa2 == 0, "tagihan tidak lunas"
        call("POST", f"/api/tagihan/{tid}/bayar", {
            "tanggal": "2026-11-01", "jumlah": 1000, "metode_bayar_id": metode["Tunai"],
        }, expect=400)
        print("  overpay ditolak (400) — benar")

        print("== klaim BPJS ==")
        kl = call("POST", "/api/klaim", {
            "tanggal_ajuan": "2026-11-01", "unit_layanan_id": unit["Rawat Jalan"],
            "jumlah": 500000, "keterangan": "UJI ALUR (hapus)",
        })
        klid = kl["id"]; created["klaim"].append(klid)

        print("== laporan & neraca ==")
        lap = call("GET", "/api/laporan?dari=2026-11-01&sampai=2026-11-01")
        print(f"  masuk={lap['masuk']} keluar={lap['keluar']} piutang_bpjs={lap['piutang_bpjs']} "
              f"laba_akrual={lap['laba_akrual']}")
        assert lap["masuk"] >= 300000, "pembayaran tidak masuk laporan"
        ner = call("GET", "/api/neraca?per=2026-11-01")
        print(f"  aset={ner['aset']['total']} ekuitas={ner['ekuitas']['total']} seimbang={ner['seimbang']}")
        assert ner["seimbang"], "neraca tidak seimbang"
        unit_rep = call("GET", "/api/laporan-unit?dari=2026-11-01&sampai=2026-11-01")
        total_laba = sum(u["laba"] for u in unit_rep["units"])
        print(f"  total laba per unit={total_laba} vs laba akrual={lap['laba_akrual']}")
        assert total_laba == lap["laba_akrual"], "laba per unit tidak menjumlah ke laba akrual"
        print("\nSEMUA LANGKAH LULUS")
    finally:
        cleanup()


def cleanup():
    print("\n== bersihkan data uji (hanya id yang dibuat skrip ini) ==")
    for klid in created["klaim"]:
        call("DELETE", f"/api/klaim/{klid}")
    for trid in created["transaksi"]:
        if trid:
            call("DELETE", f"/api/transaksi/{trid}")
    for tid in created["tagihan"]:
        call("DELETE", f"/api/tagihan/{tid}")
    for kid in created["kunjungan"]:
        call("DELETE", f"/api/kunjungan/{kid}")
    for pid in created["pasien"]:
        call("DELETE", f"/api/pasien/{pid}")
    sisa_pasien = [x for x in call("GET", "/api/pasien") if "UJI ALUR" in (x["nama"] or "")]
    print(f"  sisa pasien uji: {len(sisa_pasien)}")
    assert not sisa_pasien, "data uji masih tertinggal"


if __name__ == "__main__":
    main()
