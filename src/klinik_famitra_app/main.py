"""API modul keuangan Klinik Fa-Mitra (Tahap 1)."""
import psycopg
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import database as db
from . import seed
from . import auth

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    seed.seed()
    seed.seed_admin()
    auth.cleanup_expired_sessions()
    yield


app = FastAPI(title="Klinik Fa-Mitra App - Keuangan", lifespan=lifespan)


# ---------------- Middleware auth (semua /api kecuali login wajib token) ----------------
PUBLIC_PATHS = {"/api/login", "/api/health"}


def _user_from_request(request: Request):
    header = request.headers.get("authorization", "")
    token = header.removeprefix("Bearer ").strip()
    return auth.get_user_by_token(token)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api") and path not in PUBLIC_PATHS:
        user = _user_from_request(request)
        if user is None:
            return JSONResponse(status_code=401, content={"detail": "Belum login atau sesi berakhir"})
        request.state.user = user
    return await call_next(request)


def require_admin(request: Request):
    user = getattr(request.state, "user", None)
    if not user or user["role"] != "admin":
        raise HTTPException(403, "Hanya admin yang bisa mengelola pengguna")
    return user


# ---------------- Model input ----------------
class TransaksiIn(BaseModel):
    tanggal: str
    jenis: str
    unit_layanan_id: Optional[int] = None
    sumber_bayar_id: Optional[int] = None
    kategori_keluar_id: Optional[int] = None
    metode_bayar_id: Optional[int] = None
    tagihan_id: Optional[int] = None
    jumlah: int
    keterangan: Optional[str] = None
    dicatat_oleh: Optional[str] = None


class KlaimIn(BaseModel):
    tanggal_ajuan: str
    unit_layanan_id: Optional[int] = None
    jumlah: int
    keterangan: Optional[str] = None


class NamaIn(BaseModel):
    nama: str


class MetodeIn(BaseModel):
    nama: str
    jenis_dana: str


class TagihanIn(BaseModel):
    tanggal: str
    nama_pasien: Optional[str] = None
    unit_layanan_id: Optional[int] = None
    sumber_bayar_id: Optional[int] = None
    total: int
    keterangan: Optional[str] = None


class BayarIn(BaseModel):
    tanggal: str
    metode_bayar_id: int
    jumlah: int
    keterangan: Optional[str] = None
    dicatat_oleh: Optional[str] = None


class ModalIn(BaseModel):
    tanggal: str
    jenis: str
    jenis_dana: str
    jumlah: int
    keterangan: Optional[str] = None


class PasienIn(BaseModel):
    no_rm: Optional[str] = None
    nama: str
    nik: Optional[str] = None
    no_bpjs: Optional[str] = None
    tanggal_lahir: Optional[str] = None
    jenis_kelamin: Optional[str] = None
    alamat: Optional[str] = None
    no_telepon: Optional[str] = None


class NakesIn(BaseModel):
    nama: str
    profesi: Optional[str] = None
    sip: Optional[str] = None
    status: Optional[str] = None


class LoginIn(BaseModel):
    username: str
    password: str


class UserIn(BaseModel):
    username: str
    password: Optional[str] = None
    nama: Optional[str] = None
    role: str


class GantiPasswordIn(BaseModel):
    password_lama: str
    password_baru: str


class KunjunganIn(BaseModel):
    tanggal: str
    pasien_id: int
    unit_layanan_id: Optional[int] = None
    nakes_id: Optional[int] = None
    sumber_bayar_id: Optional[int] = None
    keluhan: Optional[str] = None


class RekamMedisIn(BaseModel):
    kunjungan_id: int
    anamnesa: Optional[str] = None
    diagnosa: Optional[str] = None
    tindakan: Optional[str] = None
    terapi: Optional[str] = None
    keterangan: Optional[str] = None


def _modal_sum(conn, kind: Optional[str] = None, until: Optional[str] = None) -> int:
    """Total modal: saldo awal + setoran - prive."""
    q = "SELECT COALESCE(SUM(CASE WHEN jenis='prive' THEN -jumlah ELSE jumlah END),0) AS v FROM modal WHERE 1=1"
    a = []
    if kind:
        q += " AND jenis_dana = %s"; a.append(kind)
    if until:
        q += " AND tanggal <= %s"; a.append(until)
    return conn.execute(q, a).fetchone()["v"]


def _balance_dana(conn, kind: str, until: Optional[str] = None) -> int:
    """Saldo kas/rekening = saldo awal + setoran - prive + (uang masuk - uang keluar)."""
    q = ("SELECT COALESCE(SUM(CASE WHEN t.jenis='masuk' THEN t.jumlah ELSE -t.jumlah END),0) AS v "
         "FROM transaksi t JOIN metode_bayar m ON t.metode_bayar_id=m.id WHERE m.jenis_dana=%s")
    a = [kind]
    if until:
        q += " AND t.tanggal <= %s"; a.append(until)
    flows = conn.execute(q, a).fetchone()["v"]
    return flows + _modal_sum(conn, kind, until)


def _metode_valid(conn, mid: Optional[int]) -> bool:
    if not mid:
        return False
    return conn.execute("SELECT id FROM metode_bayar WHERE id=%s", (mid,)).fetchone() is not None


def _sisa_tagihan(conn, tid: int) -> Optional[int]:
    tg = conn.execute("SELECT total FROM tagihan WHERE id=%s", (tid,)).fetchone()
    if tg is None:
        return None
    paid = conn.execute(
        "SELECT COALESCE(SUM(jumlah),0) AS v FROM transaksi WHERE tagihan_id=%s AND jenis='masuk'",
        (tid,),
    ).fetchone()["v"]
    return tg["total"] - paid


# ---------------- Master ----------------
@app.get("/api/master")
def get_master():
    conn = db.get_conn()
    out = {
        "unit_layanan": [dict(r) for r in conn.execute("SELECT * FROM unit_layanan ORDER BY id")],
        "sumber_bayar": [dict(r) for r in conn.execute("SELECT * FROM sumber_bayar ORDER BY id")],
        "kategori_keluar": [dict(r) for r in conn.execute("SELECT * FROM kategori_keluar ORDER BY id")],
        "metode_bayar": [dict(r) for r in conn.execute("SELECT * FROM metode_bayar ORDER BY urutan, id")],
    }
    conn.close()
    return out


@app.post("/api/master/{tipe}")
def add_master(tipe: str, body: NamaIn):
    table = {"unit_layanan": "unit_layanan", "sumber_bayar": "sumber_bayar", "kategori_keluar": "kategori_keluar"}
    if tipe not in table:
        raise HTTPException(400, "tipe tidak dikenal")
    nama = body.nama.strip()
    if not nama:
        raise HTTPException(400, "nama kosong")
    conn = db.get_conn()
    try:
        cur = conn.execute(f"INSERT INTO {table[tipe]} (nama) VALUES (%s) RETURNING id", (nama,))
        new_id = cur.fetchone()["id"]
        conn.commit()
    except Exception:
        conn.close()
        raise HTTPException(400, "nama sudah ada")
    conn.close()
    return {"id": new_id, "nama": nama}


@app.put("/api/master/{tipe}/{mid}")
def edit_master(tipe: str, mid: int, body: NamaIn):
    table = {"unit_layanan": "unit_layanan", "sumber_bayar": "sumber_bayar", "kategori_keluar": "kategori_keluar"}
    if tipe not in table:
        raise HTTPException(400, "tipe tidak dikenal")
    nama = body.nama.strip()
    if not nama:
        raise HTTPException(400, "nama kosong")
    conn = db.get_conn()
    try:
        cur = conn.execute(f"UPDATE {table[tipe]} SET nama=%s WHERE id=%s", (nama, mid))
        rc = cur.rowcount
        conn.commit()
    except psycopg.errors.IntegrityError:
        conn.close()
        raise HTTPException(400, "nama sudah ada")
    conn.close()
    if rc == 0:
        raise HTTPException(404, "data tidak ditemukan")
    return {"ok": True}


@app.delete("/api/master/{tipe}/{mid}")
def delete_master(tipe: str, mid: int):
    table = {"unit_layanan": "unit_layanan", "sumber_bayar": "sumber_bayar", "kategori_keluar": "kategori_keluar"}
    if tipe not in table:
        raise HTTPException(400, "tipe tidak dikenal")
    conn = db.get_conn()
    try:
        cur = conn.execute(f"DELETE FROM {table[tipe]} WHERE id=%s", (mid,))
        rc = cur.rowcount
        conn.commit()
    except psycopg.errors.IntegrityError:
        conn.close()
        raise HTTPException(400, "tidak bisa dihapus — masih dipakai di transaksi/klaim")
    conn.close()
    if rc == 0:
        raise HTTPException(404, "data tidak ditemukan")
    return {"ok": True}


# ---------------- Metode bayar ----------------
@app.post("/api/metode")
def add_metode(m: MetodeIn):
    nama = m.nama.strip()
    if not nama:
        raise HTTPException(400, "nama kosong")
    if m.jenis_dana not in ("kas", "bank"):
        raise HTTPException(400, "jenis dana harus kas/bank")
    conn = db.get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO metode_bayar (nama, jenis_dana, urutan) VALUES (%s,%s, (SELECT COALESCE(MAX(urutan),0)+1 FROM metode_bayar)) RETURNING id",
            (nama, m.jenis_dana),
        )
        new_id = cur.fetchone()["id"]
        conn.commit()
    except Exception:
        conn.close()
        raise HTTPException(400, "nama sudah ada")
    conn.close()
    return {"id": new_id, "nama": nama, "jenis_dana": m.jenis_dana}


@app.put("/api/metode/{mid}")
def edit_metode(mid: int, m: MetodeIn):
    nama = m.nama.strip()
    if not nama:
        raise HTTPException(400, "nama kosong")
    if m.jenis_dana not in ("kas", "bank"):
        raise HTTPException(400, "jenis dana harus kas/bank")
    conn = db.get_conn()
    try:
        cur = conn.execute("UPDATE metode_bayar SET nama=%s, jenis_dana=%s WHERE id=%s", (nama, m.jenis_dana, mid))
        rc = cur.rowcount
        conn.commit()
    except psycopg.errors.IntegrityError:
        conn.close()
        raise HTTPException(400, "nama sudah ada")
    conn.close()
    if rc == 0:
        raise HTTPException(404, "metode tidak ditemukan")
    return {"ok": True}


@app.delete("/api/metode/{mid}")
def delete_metode(mid: int):
    conn = db.get_conn()
    try:
        cur = conn.execute("DELETE FROM metode_bayar WHERE id=%s", (mid,))
        rc = cur.rowcount
        conn.commit()
    except psycopg.errors.IntegrityError:
        conn.close()
        raise HTTPException(400, "tidak bisa dihapus — sudah dipakai di transaksi")
    conn.close()
    if rc == 0:
        raise HTTPException(404, "metode tidak ditemukan")
    return {"ok": True}


# ---------------- Transaksi ----------------
@app.get("/api/transaksi")
def list_transaksi(
    dari: Optional[str] = None,
    sampai: Optional[str] = None,
    jenis: Optional[str] = None,
):
    q = (
        "SELECT t.*, u.nama AS unit, s.nama AS sumber, k.nama AS kategori, "
        "m.nama AS metode, m.jenis_dana, tg.nama_pasien AS pasien "
        "FROM transaksi t "
        "LEFT JOIN unit_layanan u ON t.unit_layanan_id=u.id "
        "LEFT JOIN sumber_bayar s ON t.sumber_bayar_id=s.id "
        "LEFT JOIN kategori_keluar k ON t.kategori_keluar_id=k.id "
        "LEFT JOIN metode_bayar m ON t.metode_bayar_id=m.id "
        "LEFT JOIN tagihan tg ON t.tagihan_id=tg.id "
        "WHERE 1=1"
    )
    args = []
    if dari:
        q += " AND t.tanggal >= %s"; args.append(dari)
    if sampai:
        q += " AND t.tanggal <= %s"; args.append(sampai)
    if jenis:
        q += " AND t.jenis = %s"; args.append(jenis)
    q += " ORDER BY t.tanggal DESC, t.id DESC"
    conn = db.get_conn()
    rows = [dict(r) for r in conn.execute(q, args)]
    conn.close()
    return rows


@app.post("/api/transaksi")
def create_transaksi(t: TransaksiIn):
    if t.jenis not in ("masuk", "keluar"):
        raise HTTPException(400, "jenis harus masuk/keluar")
    if t.jumlah <= 0:
        raise HTTPException(400, "jumlah harus > 0")
    if t.jenis == "masuk" and not (t.unit_layanan_id and t.sumber_bayar_id):
        raise HTTPException(400, "pemasukan wajib isi unit layanan & sumber bayar")
    if t.jenis == "keluar" and not t.kategori_keluar_id:
        raise HTTPException(400, "pengeluaran wajib isi kategori")
    if not t.metode_bayar_id:
        raise HTTPException(400, "metode bayar wajib dipilih (tunai/transfer/QRIS)")
    conn = db.get_conn()
    if not _metode_valid(conn, t.metode_bayar_id):
        conn.close()
        raise HTTPException(400, "metode bayar tidak valid")
    if t.tagihan_id:
        sisa = _sisa_tagihan(conn, t.tagihan_id)
        if sisa is None:
            conn.close()
            raise HTTPException(400, "tagihan tidak ditemukan")
        if t.jumlah > sisa:
            conn.close()
            raise HTTPException(400, f"jumlah melebihi sisa tagihan ({sisa})")
    cur = conn.execute(
        "INSERT INTO transaksi (tanggal, jenis, unit_layanan_id, sumber_bayar_id, kategori_keluar_id, metode_bayar_id, tagihan_id, jumlah, keterangan, dicatat_oleh) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (
            t.tanggal, t.jenis, t.unit_layanan_id, t.sumber_bayar_id, t.kategori_keluar_id,
            t.metode_bayar_id, t.tagihan_id, t.jumlah, t.keterangan, t.dicatat_oleh,
        ),
    )
    new_id = cur.fetchone()["id"]
    conn.commit()
    conn.close()
    return {"id": new_id, "ok": True}


@app.delete("/api/transaksi/{tid}")
def delete_transaksi(tid: int):
    conn = db.get_conn()
    cur = conn.execute("DELETE FROM transaksi WHERE id=%s", (tid,))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise HTTPException(404, "transaksi tidak ditemukan")
    return {"ok": True}


# ---------------- Tagihan pasien ----------------
@app.get("/api/tagihan")
def list_tagihan(
    dari: Optional[str] = None,
    sampai: Optional[str] = None,
    hanya_sisa: bool = False,
):
    q = (
        "SELECT tg.*, u.nama AS unit, s.nama AS sumber, "
        "COALESCE(p.paid,0) AS terbayar, tg.total - COALESCE(p.paid,0) AS sisa "
        "FROM tagihan tg "
        "LEFT JOIN unit_layanan u ON tg.unit_layanan_id=u.id "
        "LEFT JOIN sumber_bayar s ON tg.sumber_bayar_id=s.id "
        "LEFT JOIN (SELECT tagihan_id, SUM(jumlah) AS paid FROM transaksi "
        "           WHERE jenis='masuk' AND tagihan_id IS NOT NULL GROUP BY tagihan_id) p "
        "  ON p.tagihan_id = tg.id "
        "WHERE 1=1"
    )
    args = []
    if dari:
        q += " AND tg.tanggal >= %s"; args.append(dari)
    if sampai:
        q += " AND tg.tanggal <= %s"; args.append(sampai)
    if hanya_sisa:
        q += " AND tg.total - COALESCE(p.paid,0) > 0"
    q += " ORDER BY tg.tanggal DESC, tg.id DESC"
    conn = db.get_conn()
    rows = [dict(r) for r in conn.execute(q, args)]
    conn.close()
    return rows


@app.post("/api/tagihan")
def create_tagihan(t: TagihanIn):
    if t.total <= 0:
        raise HTTPException(400, "total tagihan harus > 0")
    conn = db.get_conn()
    cur = conn.execute(
        "INSERT INTO tagihan (tanggal, nama_pasien, unit_layanan_id, sumber_bayar_id, total, keterangan) VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
        (t.tanggal, t.nama_pasien, t.unit_layanan_id, t.sumber_bayar_id, t.total, t.keterangan),
    )
    new_id = cur.fetchone()["id"]
    conn.commit()
    conn.close()
    return {"id": new_id, "ok": True}


@app.delete("/api/tagihan/{tid}")
def delete_tagihan(tid: int):
    conn = db.get_conn()
    try:
        cur = conn.execute("DELETE FROM tagihan WHERE id=%s", (tid,))
        rc = cur.rowcount
        conn.commit()
    except psycopg.errors.IntegrityError:
        conn.close()
        raise HTTPException(400, "tidak bisa dihapus — sudah ada pembayaran. Hapus pembayarannya dulu.")
    conn.close()
    if rc == 0:
        raise HTTPException(404, "tagihan tidak ditemukan")
    return {"ok": True}


@app.post("/api/tagihan/{tid}/bayar")
def bayar_tagihan(tid: int, b: BayarIn):
    if b.jumlah <= 0:
        raise HTTPException(400, "jumlah harus > 0")
    conn = db.get_conn()
    tg = conn.execute("SELECT * FROM tagihan WHERE id=%s", (tid,)).fetchone()
    if tg is None:
        conn.close()
        raise HTTPException(404, "tagihan tidak ditemukan")
    sisa = _sisa_tagihan(conn, tid)
    if sisa is None:
        conn.close()
        raise HTTPException(404, "tagihan tidak ditemukan")
    if b.jumlah > sisa:
        conn.close()
        raise HTTPException(400, f"jumlah melebihi sisa tagihan (sisa {sisa})")
    if not _metode_valid(conn, b.metode_bayar_id):
        conn.close()
        raise HTTPException(400, "metode bayar tidak valid")
    cur = conn.execute(
        "INSERT INTO transaksi (tanggal, jenis, unit_layanan_id, sumber_bayar_id, metode_bayar_id, tagihan_id, jumlah, keterangan, dicatat_oleh) "
        "VALUES (%s, 'masuk', %s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (
            b.tanggal, tg["unit_layanan_id"], tg["sumber_bayar_id"], b.metode_bayar_id,
            tid, b.jumlah, b.keterangan, b.dicatat_oleh,
        ),
    )
    new_id = cur.fetchone()["id"]
    conn.commit()
    conn.close()
    return {"id": new_id, "ok": True, "sisa": sisa - b.jumlah}


# ---------------- Klaim BPJS ----------------
@app.get("/api/klaim")
def list_klaim(status: Optional[str] = None):
    q = "SELECT k.*, u.nama AS unit FROM klaim_bpjs k LEFT JOIN unit_layanan u ON k.unit_layanan_id=u.id WHERE 1=1"
    args = []
    if status:
        q += " AND k.status = %s"; args.append(status)
    q += " ORDER BY k.tanggal_ajuan DESC, k.id DESC"
    conn = db.get_conn()
    rows = [dict(r) for r in conn.execute(q, args)]
    conn.close()
    return rows


@app.post("/api/klaim")
def create_klaim(k: KlaimIn):
    if k.jumlah <= 0:
        raise HTTPException(400, "jumlah harus > 0")
    conn = db.get_conn()
    cur = conn.execute(
        "INSERT INTO klaim_bpjs (tanggal_ajuan, unit_layanan_id, jumlah, keterangan) VALUES (%s,%s,%s,%s) RETURNING id",
        (k.tanggal_ajuan, k.unit_layanan_id, k.jumlah, k.keterangan),
    )
    new_id = cur.fetchone()["id"]
    conn.commit()
    conn.close()
    return {"id": new_id, "ok": True}


@app.post("/api/klaim/{kid}/cair")
def cairkan_klaim(kid: int, body: dict):
    tanggal_cair = body.get("tanggal_cair")
    conn = db.get_conn()
    cur = conn.execute(
        "UPDATE klaim_bpjs SET status='cair', tanggal_cair=%s WHERE id=%s AND status='diajukan'",
        (tanggal_cair, kid),
    )
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise HTTPException(404, "klaim tidak ditemukan atau sudah cair")
    return {"ok": True}


@app.delete("/api/klaim/{kid}")
def delete_klaim(kid: int):
    conn = db.get_conn()
    cur = conn.execute("DELETE FROM klaim_bpjs WHERE id=%s", (kid,))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise HTTPException(404, "klaim tidak ditemukan")
    return {"ok": True}


# ---------------- Laporan ----------------
@app.get("/api/laporan")
def laporan(dari: Optional[str] = None, sampai: Optional[str] = None):
    conn = db.get_conn()
    cond = []
    args = []
    if dari:
        cond.append("t.tanggal >= %s"); args.append(dari)
    if sampai:
        cond.append("t.tanggal <= %s"); args.append(sampai)
    where = (" AND " + " AND ".join(cond)) if cond else ""

    masuk = conn.execute(
        f"SELECT COALESCE(SUM(jumlah),0) AS v FROM transaksi t WHERE t.jenis='masuk'{where}", args
    ).fetchone()["v"]

    keluar = conn.execute(
        f"SELECT COALESCE(SUM(jumlah),0) AS v FROM transaksi t WHERE t.jenis='keluar'{where}", args
    ).fetchone()["v"]

    piutang = conn.execute(
        "SELECT COALESCE(SUM(jumlah),0) AS v FROM klaim_bpjs WHERE status='diajukan'"
    ).fetchone()["v"]

    # Piutang yang DIAKUI pada periode terpilih (dasar laba akrual).
    # Kartu piutang di dashboard tetap memakai saldo outstanding di atas.
    pcond, pargs = [], []
    if dari:
        pcond.append("tanggal_ajuan >= %s"); pargs.append(dari)
    if sampai:
        pcond.append("tanggal_ajuan <= %s"); pargs.append(sampai)
    pw = (" AND " + " AND ".join(pcond)) if pcond else ""
    piutang_periode = conn.execute(
        f"SELECT COALESCE(SUM(jumlah),0) AS v FROM klaim_bpjs WHERE status='diajukan'{pw}", pargs
    ).fetchone()["v"]

    # Saldo kas & rekening = SALDO berjalan (bukan mutasi periode):
    # saldo awal + setoran modal - prive + (uang masuk - uang keluar).
    kas_tunai = _balance_dana(conn, "kas", sampai)
    saldo_bank = _balance_dana(conn, "bank", sampai)
    modal_total = _modal_sum(conn, None, sampai)

    piutang_pasien = conn.execute(
        "SELECT COALESCE(SUM(sisa),0) AS v FROM ("
        "  SELECT tg.total - COALESCE((SELECT SUM(x.jumlah) FROM transaksi x "
        "    WHERE x.tagihan_id=tg.id AND x.jenis='masuk'),0) AS sisa FROM tagihan tg"
        ") WHERE sisa > 0"
    ).fetchone()["v"]

    tcond, targs = [], []
    if dari:
        tcond.append("tanggal >= %s"); targs.append(dari)
    if sampai:
        tcond.append("tanggal <= %s"); targs.append(sampai)
    tw = (" AND " + " AND ".join(tcond)) if tcond else ""
    piutang_pasien_periode = conn.execute(
        "SELECT COALESCE(SUM(sisa),0) AS v FROM ("
        "  SELECT tg.total - COALESCE((SELECT SUM(x.jumlah) FROM transaksi x "
        "    WHERE x.tagihan_id=tg.id AND x.jenis='masuk'),0) AS sisa, tg.tanggal AS tanggal FROM tagihan tg"
        f") WHERE sisa > 0{tw}", targs
    ).fetchone()["v"]

    per_unit = [dict(r) for r in conn.execute(
        f"SELECT u.nama, COALESCE(SUM(t.jumlah),0) AS total FROM transaksi t JOIN unit_layanan u ON t.unit_layanan_id=u.id WHERE t.jenis='masuk'{where} GROUP BY u.id ORDER BY total DESC",
        args,
    )]

    per_sumber = [dict(r) for r in conn.execute(
        f"SELECT s.nama, COALESCE(SUM(t.jumlah),0) AS total FROM transaksi t JOIN sumber_bayar s ON t.sumber_bayar_id=s.id WHERE t.jenis='masuk'{where} GROUP BY s.id ORDER BY total DESC",
        args,
    )]

    per_kategori = [dict(r) for r in conn.execute(
        f"SELECT k.nama, COALESCE(SUM(t.jumlah),0) AS total FROM transaksi t JOIN kategori_keluar k ON t.kategori_keluar_id=k.id WHERE t.jenis='keluar'{where} GROUP BY k.id ORDER BY total DESC",
        args,
    )]

    per_metode = [dict(r) for r in conn.execute(
        f"SELECT m.nama, m.jenis_dana, COALESCE(SUM(t.jumlah),0) AS total FROM transaksi t JOIN metode_bayar m ON t.metode_bayar_id=m.id WHERE t.jenis='masuk'{where} GROUP BY m.id ORDER BY total DESC",
        args,
    )]

    conn.close()

    laba_kas = masuk - keluar
    pendapatan_akrual = masuk + piutang_periode + piutang_pasien_periode
    laba_akrual = pendapatan_akrual - keluar

    return {
        "masuk": masuk,
        "keluar": keluar,
        "saldo": laba_kas,
        "kas_tunai": kas_tunai,
        "saldo_bank": saldo_bank,
        "modal_total": modal_total,
        "piutang_bpjs": piutang,
        "piutang_pasien": piutang_pasien,
        "piutang_bpjs_periode": piutang_periode,
        "piutang_pasien_periode": piutang_pasien_periode,
        "pendapatan_akrual": pendapatan_akrual,
        "laba_akrual": laba_akrual,
        "per_unit": per_unit,
        "per_sumber": per_sumber,
        "per_kategori": per_kategori,
        "per_metode": per_metode,
    }


# ---------------- Modal & saldo awal ----------------
@app.get("/api/modal")
def list_modal():
    conn = db.get_conn()
    rows = [dict(r) for r in conn.execute("SELECT * FROM modal ORDER BY tanggal DESC, id DESC")]
    conn.close()
    return rows


@app.post("/api/modal")
def create_modal(m: ModalIn):
    if m.jenis not in ("saldo_awal", "setoran", "prive"):
        raise HTTPException(400, "jenis harus saldo_awal/setoran/prive")
    if m.jenis_dana not in ("kas", "bank"):
        raise HTTPException(400, "jenis dana harus kas/bank")
    if m.jumlah <= 0:
        raise HTTPException(400, "jumlah harus > 0")
    conn = db.get_conn()
    cur = conn.execute(
        "INSERT INTO modal (tanggal, jenis, jenis_dana, jumlah, keterangan) VALUES (%s,%s,%s,%s,%s) RETURNING id",
        (m.tanggal, m.jenis, m.jenis_dana, m.jumlah, m.keterangan),
    )
    new_id = cur.fetchone()["id"]
    conn.commit()
    conn.close()
    return {"id": new_id, "ok": True}


@app.delete("/api/modal/{mid}")
def delete_modal(mid: int):
    conn = db.get_conn()
    cur = conn.execute("DELETE FROM modal WHERE id=%s", (mid,))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise HTTPException(404, "data modal tidak ditemukan")
    return {"ok": True}


# ---------------- Laporan per unit layanan ----------------
@app.get("/api/laporan-unit")
def laporan_unit(dari: Optional[str] = None, sampai: Optional[str] = None):
    conn = db.get_conn()

    def period(alias: str) -> tuple[str, list]:
        c = []
        a = []
        if dari:
            c.append(f"{alias}.tanggal >= %s"); a.append(dari)
        if sampai:
            c.append(f"{alias}.tanggal <= %s"); a.append(sampai)
        return (" AND " + " AND ".join(c)) if c else "", a

    units = [dict(r) for r in conn.execute("SELECT id, nama FROM unit_layanan ORDER BY id")]

    w, a = period("t")
    kas = {r["uid"]: r["total"] for r in conn.execute(
        "SELECT t.unit_layanan_id AS uid, COALESCE(SUM(t.jumlah),0) AS total "
        f"FROM transaksi t WHERE t.jenis='masuk'{w} GROUP BY t.unit_layanan_id", a)}

    w, a = period("t")
    beban = {r["uid"]: r["total"] for r in conn.execute(
        "SELECT t.unit_layanan_id AS uid, COALESCE(SUM(t.jumlah),0) AS total "
        f"FROM transaksi t WHERE t.jenis='keluar'{w} GROUP BY t.unit_layanan_id", a)}

    c = ["status='diajukan'"]
    a = []
    if dari:
        c.append("tanggal_ajuan >= %s"); a.append(dari)
    if sampai:
        c.append("tanggal_ajuan <= %s"); a.append(sampai)
    bpjs = {r["uid"]: r["total"] for r in conn.execute(
        f"SELECT unit_layanan_id AS uid, COALESCE(SUM(jumlah),0) AS total FROM klaim_bpjs WHERE {' AND '.join(c)} GROUP BY unit_layanan_id", a)}

    sub = ("SELECT tg.unit_layanan_id AS uid, tg.tanggal AS tanggal, "
           "tg.total - COALESCE((SELECT SUM(x.jumlah) FROM transaksi x "
           "WHERE x.tagihan_id=tg.id AND x.jenis='masuk'),0) AS sisa FROM tagihan tg")
    c = ["sisa > 0"]
    a = []
    if dari:
        c.append("tanggal >= %s"); a.append(dari)
    if sampai:
        c.append("tanggal <= %s"); a.append(sampai)
    pp = {r["uid"]: r["total"] for r in conn.execute(
        f"SELECT uid, COALESCE(SUM(sisa),0) AS total FROM ({sub}) WHERE {' AND '.join(c)} GROUP BY uid", a)}

    beban_bersama = beban.get(None, 0)
    rows = []
    total_basis = 0
    for u in units:
        k = kas.get(u["id"], 0)
        b = bpjs.get(u["id"], 0)
        p = pp.get(u["id"], 0)
        akrual = k + b + p
        total_basis += akrual
        rows.append({
            "id": u["id"], "nama": u["nama"],
            "pendapatan_kas": k, "piutang_bpjs": b, "piutang_pasien": p,
            "pendapatan_akrual": akrual,
            "beban_langsung": beban.get(u["id"], 0),
            "beban_alokasi": 0, "laba": 0, "margin": None,
        })

    n = len(rows)
    for r in rows:
        share = (r["pendapatan_akrual"] / total_basis) if total_basis > 0 else (1 / n if n else 0)
        r["beban_alokasi"] = round(beban_bersama * share)

    if rows and total_basis > 0:
        diff = beban_bersama - sum(r["beban_alokasi"] for r in rows)
        if diff:
            biggest = max(rows, key=lambda r: r["pendapatan_akrual"])
            biggest["beban_alokasi"] += diff

    for r in rows:
        r["laba"] = r["pendapatan_akrual"] - r["beban_langsung"] - r["beban_alokasi"]
        r["margin"] = (100 * r["laba"] / r["pendapatan_akrual"]) if r["pendapatan_akrual"] > 0 else None

    rows.sort(key=lambda r: r["pendapatan_akrual"], reverse=True)

    total: dict = {
        "pendapatan_kas": sum(r["pendapatan_kas"] for r in rows),
        "piutang_bpjs": sum(r["piutang_bpjs"] for r in rows),
        "piutang_pasien": sum(r["piutang_pasien"] for r in rows),
        "pendapatan_akrual": sum(r["pendapatan_akrual"] for r in rows),
        "beban_langsung": sum(r["beban_langsung"] for r in rows),
        "beban_alokasi": sum(r["beban_alokasi"] for r in rows),
        "laba": sum(r["laba"] for r in rows),
    }
    total["margin"] = (100 * total["laba"] / total["pendapatan_akrual"]) if total["pendapatan_akrual"] > 0 else None

    conn.close()
    return {"units": rows, "total": total, "beban_bersama": beban_bersama, "dasar": "proporsi_pendapatan"}


# ---------------- Neraca ----------------
@app.get("/api/neraca")
def neraca(per: Optional[str] = None):
    conn = db.get_conn()
    kas = _balance_dana(conn, "kas", per)
    bank = _balance_dana(conn, "bank", per)

    q = "SELECT COALESCE(SUM(jumlah),0) AS v FROM klaim_bpjs WHERE status='diajukan'"
    a = []
    if per:
        q += " AND tanggal_ajuan <= %s"; a.append(per)
    piutang_bpjs = conn.execute(q, a).fetchone()["v"]

    sub = ("SELECT tg.total - COALESCE((SELECT SUM(x.jumlah) FROM transaksi x "
           "WHERE x.tagihan_id=tg.id AND x.jenis='masuk'),0) AS sisa, tg.tanggal AS tanggal FROM tagihan tg")
    c = ["sisa > 0"]
    a = []
    if per:
        c.append("tanggal <= %s"); a.append(per)
    piutang_pasien = conn.execute(
        f"SELECT COALESCE(SUM(sisa),0) AS v FROM ({sub}) WHERE {' AND '.join(c)}", a
    ).fetchone()["v"]

    def total_journal(jenis: str) -> int:
        q = "SELECT COALESCE(SUM(t.jumlah),0) AS v FROM transaksi t WHERE t.jenis=%s"
        a = [jenis]
        if per:
            q += " AND t.tanggal <= %s"; a.append(per)
        return conn.execute(q, a).fetchone()["v"]

    pendapatan = total_journal("masuk")
    beban = total_journal("keluar")
    laba = pendapatan + piutang_bpjs + piutang_pasien - beban
    modal = _modal_sum(conn, None, per)

    aset_total = kas + bank + piutang_bpjs + piutang_pasien
    ekuitas_total = modal + laba
    conn.close()
    return {
        "per": per,
        "aset": {
            "kas_tunai": kas, "saldo_bank": bank,
            "piutang_bpjs": piutang_bpjs, "piutang_pasien": piutang_pasien,
            "total": aset_total,
        },
        "ekuitas": {"modal": modal, "laba_berjalan": laba, "total": ekuitas_total},
        "seimbang": aset_total == ekuitas_total,
    }


# ---------------- Tren harian (untuk grafik) ----------------
@app.get("/api/tren")
def tren(dari: Optional[str] = None, sampai: Optional[str] = None):
    conn = db.get_conn()
    end = date.fromisoformat(sampai) if sampai else date.today()
    start = date.fromisoformat(dari) if dari else end - timedelta(days=29)
    if start > end:
        start, end = end, start
    if (end - start).days > 366:
        start = end - timedelta(days=366)
    rows = {r["tanggal"]: r for r in conn.execute(
        "SELECT tanggal, "
        "COALESCE(SUM(CASE WHEN jenis='masuk' THEN jumlah ELSE 0 END),0) AS masuk, "
        "COALESCE(SUM(CASE WHEN jenis='keluar' THEN jumlah ELSE 0 END),0) AS keluar "
        "FROM transaksi WHERE tanggal >= %s AND tanggal <= %s GROUP BY tanggal",
        (start.isoformat(), end.isoformat()),
    )}
    conn.close()
    out = []
    d = start
    while d <= end:
        k = d.isoformat()
        r = rows.get(k)
        out.append({"tanggal": k, "masuk": r["masuk"] if r else 0, "keluar": r["keluar"] if r else 0})
        d += timedelta(days=1)
    return out


# ---------------- Master pasien & nakes (Tahap 2) ----------------
@app.get("/api/pasien")
def list_pasien(cari: Optional[str] = None):
    q = "SELECT * FROM pasien WHERE 1=1"
    args = []
    if cari:
        q += " AND (nama LIKE %s OR no_rm LIKE %s OR nik LIKE %s OR no_bpjs LIKE %s)"
        like = f"%{cari}%"
        args += [like, like, like, like]
    q += " ORDER BY id DESC"
    conn = db.get_conn()
    rows = [dict(r) for r in conn.execute(q, args)]
    conn.close()
    return rows


@app.post("/api/pasien")
def create_pasien(p: PasienIn):
    nama = p.nama.strip()
    if not nama:
        raise HTTPException(400, "nama wajib diisi")
    if p.jenis_kelamin and p.jenis_kelamin not in ("L", "P"):
        raise HTTPException(400, "jenis kelamin harus L/P")
    conn = db.get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO pasien (no_rm, nama, nik, no_bpjs, tanggal_lahir, jenis_kelamin, alamat, no_telepon) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
            (p.no_rm, nama, p.nik, p.no_bpjs, p.tanggal_lahir, p.jenis_kelamin, p.alamat, p.no_telepon),
        )
        new_id = cur.fetchone()["id"]
        if not p.no_rm:
            conn.execute("UPDATE pasien SET no_rm=%s WHERE id=%s", (f"RM-{new_id:06d}", new_id))
        conn.commit()
    except psycopg.errors.IntegrityError:
        conn.close()
        raise HTTPException(400, "nomor rekam medis sudah ada")
    conn.close()
    return {"id": new_id, "ok": True}


@app.put("/api/pasien/{pid}")
def edit_pasien(pid: int, p: PasienIn):
    nama = p.nama.strip()
    if not nama:
        raise HTTPException(400, "nama wajib diisi")
    if p.jenis_kelamin and p.jenis_kelamin not in ("L", "P"):
        raise HTTPException(400, "jenis kelamin harus L/P")
    conn = db.get_conn()
    try:
        cur = conn.execute(
            "UPDATE pasien SET no_rm=%s, nama=%s, nik=%s, no_bpjs=%s, tanggal_lahir=%s, jenis_kelamin=%s, alamat=%s, no_telepon=%s WHERE id=%s",
            (p.no_rm, nama, p.nik, p.no_bpjs, p.tanggal_lahir, p.jenis_kelamin, p.alamat, p.no_telepon, pid),
        )
        rc = cur.rowcount
        conn.commit()
    except psycopg.errors.IntegrityError:
        conn.close()
        raise HTTPException(400, "nomor rekam medis sudah ada")
    conn.close()
    if rc == 0:
        raise HTTPException(404, "pasien tidak ditemukan")
    return {"ok": True}


@app.delete("/api/pasien/{pid}")
def delete_pasien(pid: int):
    conn = db.get_conn()
    cur = conn.execute("DELETE FROM pasien WHERE id=%s", (pid,))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise HTTPException(404, "pasien tidak ditemukan")
    return {"ok": True}


@app.get("/api/nakes")
def list_nakes():
    conn = db.get_conn()
    rows = [dict(r) for r in conn.execute("SELECT * FROM nakes ORDER BY id DESC")]
    conn.close()
    return rows


@app.post("/api/nakes")
def create_nakes(n: NakesIn):
    nama = n.nama.strip()
    if not nama:
        raise HTTPException(400, "nama wajib diisi")
    status = n.status if n.status in ("aktif", "nonaktif") else "aktif"
    conn = db.get_conn()
    cur = conn.execute(
        "INSERT INTO nakes (nama, profesi, sip, status) VALUES (%s,%s,%s,%s) RETURNING id",
        (nama, n.profesi, n.sip, status),
    )
    new_id = cur.fetchone()["id"]
    conn.commit()
    conn.close()
    return {"id": new_id, "ok": True}


@app.put("/api/nakes/{nid}")
def edit_nakes(nid: int, n: NakesIn):
    nama = n.nama.strip()
    if not nama:
        raise HTTPException(400, "nama wajib diisi")
    status = n.status if n.status in ("aktif", "nonaktif") else "aktif"
    conn = db.get_conn()
    cur = conn.execute(
        "UPDATE nakes SET nama=%s, profesi=%s, sip=%s, status=%s WHERE id=%s",
        (nama, n.profesi, n.sip, status, nid),
    )
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise HTTPException(404, "nakes tidak ditemukan")
    return {"ok": True}


@app.delete("/api/nakes/{nid}")
def delete_nakes(nid: int):
    conn = db.get_conn()
    cur = conn.execute("DELETE FROM nakes WHERE id=%s", (nid,))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise HTTPException(404, "nakes tidak ditemukan")
    return {"ok": True}


# ---------------- Pendaftaran & rekam medis (Tahap 3) ----------------
@app.get("/api/kunjungan")
def list_kunjungan(tanggal: Optional[str] = None):
    q = (
        "SELECT k.*, p.nama AS pasien_nama, p.no_rm, u.nama AS unit, "
        "n.nama AS nakes_nama, s.nama AS sumber, "
        "COALESCE(r.id,0) AS ada_rekam "
        "FROM kunjungan k "
        "JOIN pasien p ON k.pasien_id = p.id "
        "LEFT JOIN unit_layanan u ON k.unit_layanan_id = u.id "
        "LEFT JOIN nakes n ON k.nakes_id = n.id "
        "LEFT JOIN sumber_bayar s ON k.sumber_bayar_id = s.id "
        "LEFT JOIN rekam_medis r ON r.kunjungan_id = k.id "
        "WHERE 1=1"
    )
    args = []
    if tanggal:
        q += " AND k.tanggal = %s"
        args.append(tanggal)
    q += " ORDER BY k.tanggal DESC, k.id DESC"
    conn = db.get_conn()
    rows = [dict(r) for r in conn.execute(q, args)]
    conn.close()
    return rows


@app.post("/api/kunjungan")
def create_kunjungan(k: KunjunganIn):
    conn = db.get_conn()
    if not conn.execute("SELECT id FROM pasien WHERE id=%s", (k.pasien_id,)).fetchone():
        conn.close()
        raise HTTPException(400, "pasien tidak ditemukan")
    if k.unit_layanan_id and not conn.execute("SELECT id FROM unit_layanan WHERE id=%s", (k.unit_layanan_id,)).fetchone():
        conn.close()
        raise HTTPException(400, "unit layanan tidak ditemukan")
    if k.nakes_id and not conn.execute("SELECT id FROM nakes WHERE id=%s", (k.nakes_id,)).fetchone():
        conn.close()
        raise HTTPException(400, "nakes tidak ditemukan")
    if k.sumber_bayar_id and not conn.execute("SELECT id FROM sumber_bayar WHERE id=%s", (k.sumber_bayar_id,)).fetchone():
        conn.close()
        raise HTTPException(400, "sumber bayar tidak ditemukan")
    # no antrian otomatis: urutan per tanggal
    n = conn.execute(
        "SELECT COUNT(*) AS c FROM kunjungan WHERE tanggal=%s", (k.tanggal,)
    ).fetchone()["c"]
    no_antrian = f"{n + 1:03d}"
    cur = conn.execute(
        "INSERT INTO kunjungan (tanggal, no_antrian, pasien_id, unit_layanan_id, nakes_id, sumber_bayar_id, keluhan) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (k.tanggal, no_antrian, k.pasien_id, k.unit_layanan_id, k.nakes_id, k.sumber_bayar_id, k.keluhan),
    )
    new_id = cur.fetchone()["id"]
    conn.commit()
    conn.close()
    return {"id": new_id, "no_antrian": no_antrian, "ok": True}


@app.put("/api/kunjungan/{kid}")
def edit_kunjungan(kid: int, k: KunjunganIn):
    conn = db.get_conn()
    cur = conn.execute(
        "UPDATE kunjungan SET tanggal=%s, pasien_id=%s, unit_layanan_id=%s, nakes_id=%s, sumber_bayar_id=%s, keluhan=%s "
        "WHERE id=%s",
        (k.tanggal, k.pasien_id, k.unit_layanan_id, k.nakes_id, k.sumber_bayar_id, k.keluhan, kid),
    )
    rc = cur.rowcount
    conn.commit()
    conn.close()
    if rc == 0:
        raise HTTPException(404, "kunjungan tidak ditemukan")
    return {"ok": True}


@app.post("/api/kunjungan/{kid}/status")
def status_kunjungan(kid: int, body: dict):
    status = body.get("status")
    if status not in ("menunggu", "diperiksa", "selesai", "batal"):
        raise HTTPException(400, "status tidak valid")
    conn = db.get_conn()
    cur = conn.execute("UPDATE kunjungan SET status=%s WHERE id=%s", (status, kid))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise HTTPException(404, "kunjungan tidak ditemukan")
    return {"ok": True}


@app.delete("/api/kunjungan/{kid}")
def delete_kunjungan(kid: int):
    conn = db.get_conn()
    conn.execute("DELETE FROM rekam_medis WHERE kunjungan_id=%s", (kid,))
    cur = conn.execute("DELETE FROM kunjungan WHERE id=%s", (kid,))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise HTTPException(404, "kunjungan tidak ditemukan")
    return {"ok": True}


@app.get("/api/rekam-medis/{kid}")
def get_rekam_medis(kid: int):
    conn = db.get_conn()
    row = conn.execute("SELECT * FROM rekam_medis WHERE kunjungan_id=%s", (kid,)).fetchone()
    conn.close()
    return dict(row) if row else None


@app.post("/api/rekam-medis")
def save_rekam_medis(rm: RekamMedisIn):
    conn = db.get_conn()
    if not conn.execute("SELECT id FROM kunjungan WHERE id=%s", (rm.kunjungan_id,)).fetchone():
        conn.close()
        raise HTTPException(404, "kunjungan tidak ditemukan")
    cur = conn.execute(
        "INSERT INTO rekam_medis (kunjungan_id, anamnesa, diagnosa, tindakan, terapi, keterangan) "
        "VALUES (%s,%s,%s,%s,%s,%s) "
        "ON CONFLICT (kunjungan_id) DO UPDATE SET anamnesa=EXCLUDED.anamnesa, diagnosa=EXCLUDED.diagnosa, "
        "tindakan=EXCLUDED.tindakan, terapi=EXCLUDED.terapi, keterangan=EXCLUDED.keterangan",
        (rm.kunjungan_id, rm.anamnesa, rm.diagnosa, rm.tindakan, rm.terapi, rm.keterangan),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


# ---------------- Auth: login, logout, profil, ganti password, kelola user ----------------
@app.post("/api/login")
def login(body: LoginIn):
    conn = db.get_conn()
    row = conn.execute("SELECT * FROM users WHERE username=%s", (body.username.strip(),)).fetchone()
    if row is None or not auth.verify_password(body.password, row["password_hash"]):
        conn.close()
        raise HTTPException(401, "username atau password salah")
    token = auth.create_session(conn, row["id"])
    conn.close()
    return {"token": token, "user": {"id": row["id"], "username": row["username"], "nama": row["nama"], "role": row["role"]}}


@app.post("/api/logout")
def logout(request: Request):
    header = request.headers.get("authorization", "")
    token = header.removeprefix("Bearer ").strip()
    if token:
        auth.delete_session(token)
    return {"ok": True}


@app.get("/api/me")
def me(request: Request):
    return getattr(request.state, "user", None)


@app.post("/api/ganti-password")
def ganti_password(request: Request, body: GantiPasswordIn):
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(401, "belum login")
    if not body.password_baru or len(body.password_baru) < 6:
        raise HTTPException(400, "password baru minimal 6 karakter")
    conn = db.get_conn()
    row = conn.execute("SELECT * FROM users WHERE id=%s", (user["id"],)).fetchone()
    if row is None or not auth.verify_password(body.password_lama, row["password_hash"]):
        conn.close()
        raise HTTPException(400, "password lama salah")
    conn.execute("UPDATE users SET password_hash=%s WHERE id=%s", (auth.hash_password(body.password_baru), user["id"]))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/api/users")
def list_users(request: Request):
    require_admin(request)
    conn = db.get_conn()
    rows = [dict(r) for r in conn.execute("SELECT id, username, nama, role, created_at FROM users ORDER BY id")]
    conn.close()
    return rows


@app.post("/api/users")
def create_user(request: Request, body: UserIn):
    require_admin(request)
    username = body.username.strip()
    if not username:
        raise HTTPException(400, "username wajib diisi")
    if body.role not in ("admin", "petugas"):
        raise HTTPException(400, "role harus admin/petugas")
    password = body.password or ""
    if len(password) < 6:
        raise HTTPException(400, "password minimal 6 karakter")
    conn = db.get_conn()
    try:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, nama, role) VALUES (%s,%s,%s,%s) RETURNING id",
            (username, auth.hash_password(password), body.nama, body.role),
        )
        new_id = cur.fetchone()["id"]
        conn.commit()
    except psycopg.errors.IntegrityError:
        conn.close()
        raise HTTPException(400, "username sudah ada")
    conn.close()
    return {"id": new_id, "ok": True}


@app.put("/api/users/{uid}")
def edit_user(request: Request, uid: int, body: UserIn):
    require_admin(request)
    if body.role not in ("admin", "petugas"):
        raise HTTPException(400, "role harus admin/petugas")
    conn = db.get_conn()
    if body.password:
        if len(body.password) < 6:
            conn.close()
            raise HTTPException(400, "password minimal 6 karakter")
        conn.execute(
            "UPDATE users SET username=%s, nama=%s, role=%s, password_hash=%s WHERE id=%s",
            (body.username.strip(), body.nama, body.role, auth.hash_password(body.password), uid),
        )
    else:
        conn.execute(
            "UPDATE users SET username=%s, nama=%s, role=%s WHERE id=%s",
            (body.username.strip(), body.nama, body.role, uid),
        )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/users/{uid}")
def delete_user(request: Request, uid: int):
    require_admin(request)
    me = getattr(request.state, "user", None)
    if me and me["id"] == uid:
        raise HTTPException(400, "tidak bisa menghapus akun sendiri")
    conn = db.get_conn()
    cur = conn.execute("DELETE FROM users WHERE id=%s", (uid,))
    conn.execute("DELETE FROM sessions WHERE user_id=%s", (uid,))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise HTTPException(404, "user tidak ditemukan")
    return {"ok": True}


# ---------------- Frontend ----------------
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/api/health")
def health():
    """Cek kesehatan untuk health check hosting (Render): app hidup + DB terjangkau."""
    try:
        conn = db.get_conn()
        try:
            conn.execute("SELECT 1")
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 - laporkan apa pun sebagai tidak sehat
        return JSONResponse(
            status_code=503,
            content={"ok": False, "db": db.safe_target(), "error": str(exc)},
        )
    return {"ok": True, "db": db.safe_target()}


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")
