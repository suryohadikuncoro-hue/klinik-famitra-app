// Klinik Fa-Mitra — Keuangan (Tahap 1)

const $ = (id) => document.getElementById(id);
const rupiah = (n) => 'Rp' + (Number(n) || 0).toLocaleString('id-ID');
const today = new Date();
// Tanggal LOKAL (bukan toISOString/UTC — sebelum 07:00 WIB UTC masih kemarin)
const fmt = (d) => d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
const monthStart = fmt(new Date(today.getFullYear(), today.getMonth(), 1));
const todayStr = fmt(today);

let MASTER = { unit_layanan: [], sumber_bayar: [], kategori_keluar: [], metode_bayar: [] };
let currentView = 'dashboard';
let AUTH_TOKEN = localStorage.getItem('kfm_token') || '';
let CURRENT_USER = null;

function showLogin() {
  $('login-screen').classList.remove('hidden');
}
function hideLogin() {
  $('login-screen').classList.add('hidden');
}

async function api(path, opts) {
  opts = opts || {};
  const headers = Object.assign({}, opts.headers || {});
  if (AUTH_TOKEN) headers['Authorization'] = 'Bearer ' + AUTH_TOKEN;
  const res = await fetch(path, Object.assign({}, opts, { headers }));
  if (res.status === 401) {
    AUTH_TOKEN = '';
    localStorage.removeItem('kfm_token');
    CURRENT_USER = null;
    showLogin();
    throw new Error('Sesi berakhir, silakan login ulang');
  }
  if (!res.ok) {
    const e = await res.json().catch(() => ({}));
    throw new Error(e.detail || 'Terjadi kesalahan');
  }
  return res.json();
}

function postJSON(path, body, method) {
  return api(path, {
    method: method || 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

// ---------- init ----------
async function loadMaster() {
  MASTER = await api('/api/master');
  fillSelect('t-unit', MASTER.unit_layanan);
  fillSelect('t-sumber', MASTER.sumber_bayar);
  fillSelect('t-kategori', MASTER.kategori_keluar);
  fillSelect('t-unit-keluar', MASTER.unit_layanan, '— (beban bersama)');
  fillSelect('t-metode', MASTER.metode_bayar);
  fillSelect('tg-unit', MASTER.unit_layanan, '—');
  // Tagihan pasien tidak boleh bersumber BPJS: piutang BPJS dibentuk otomatis
  // dari menu Transaksi, jadi opsi BPJS disembunyikan dari form ini.
  fillSelect('tg-sumber', MASTER.sumber_bayar.filter((s) => !s.is_bpjs));
  fillSelect('kl-metode', MASTER.metode_bayar);
  syncBpjsMode();
  renderMaster();
}

function fillSelect(id, items, placeholder) {
  const el = $(id);
  if (!el) return;
  el.innerHTML = '';
  if (placeholder) el.innerHTML = '<option value="">' + placeholder + '</option>';
  items.forEach((it) => {
    const o = document.createElement('option');
    o.value = it.id;
    o.textContent = it.nama;
    el.appendChild(o);
  });
}

function metodeOptions() {
  return MASTER.metode_bayar.map((m) =>
    '<option value="' + m.id + '">' + esc(m.nama) + ' · ' + (m.jenis_dana === 'kas' ? 'tunai' : 'rekening') + '</option>'
  ).join('');
}

// ---------- tabs ----------
document.querySelectorAll('[data-view]').forEach((btn) => {
  btn.addEventListener('click', () => switchView(btn.dataset.view));
});

$('mobile-more-toggle').addEventListener('click', () => {
  $('mobile-more').showModal();
  $('mobile-more-toggle').setAttribute('aria-expanded', 'true');
});
$('mobile-more-close').addEventListener('click', closeMobileMore);
$('mobile-more').addEventListener('cancel', (event) => {
  event.preventDefault();
  closeMobileMore();
});
$('mobile-more').addEventListener('close', () => {
  $('mobile-more-toggle').setAttribute('aria-expanded', 'false');
  $('mobile-more-toggle').focus();
});
// Native dialog traps focus; dismiss it when returning to the desktop layout.
globalThis.matchMedia?.('(max-width: 767px)').addEventListener('change', closeMobileMore);

function switchView(name) {
  closeMobileMore();
  document.querySelectorAll('[aria-controls="mobile-more"]').forEach((button) => {
    button.classList.toggle('active', ['pasien', 'kunjungan', 'master'].includes(name));
  });
  currentView = name;
  document.querySelectorAll('.view').forEach((v) => v.classList.remove('active'));
  document.querySelectorAll('[data-view]').forEach((b) => {
    const active = b.dataset.view === name;
    b.classList.toggle('active', active);
    if (active) b.setAttribute('aria-current', 'page');
    else b.removeAttribute('aria-current');
  });
  $('view-' + name).classList.add('active');
  if (name === 'dashboard') renderDashboard();
  if (name === 'transaksi') renderTransaksi();
  if (name === 'tagihan') {
    if (tgMode === 'klaim') renderKlaim(); else renderTagihan();
  }
  if (name === 'pasien') {
    if (psMode === 'nakes') renderNakes(); else renderPasien();
  }
  if (name === 'kunjungan') renderKunjungan();
  if (name === 'laporan') {
    const active = ['unit', 'neraca', 'modal'].find((k) => $('lap-' + k).classList.contains('active')) || 'unit';
    renderLaporanSub(active);
  }
  if (name === 'master') { renderMaster(); renderUsers(); }
}

function closeMobileMore() {
  if ($('mobile-more').open) $('mobile-more').close();
}

// mode Tagihan: pasien / klaim dalam satu kartu (pola sama seperti Transaksi)
let tgMode = 'pasien';

function setTagihanMode(mode) {
  tgMode = mode;
  document.querySelectorAll('#form-tagihan .seg [data-tg]').forEach((b) => b.classList.toggle('active', b.dataset.tg === mode));
  $('tg-mode').value = mode;
  $('tg-fields-pasien').classList.toggle('hidden', mode !== 'pasien');
  $('tg-fields-klaim').classList.toggle('hidden', mode !== 'klaim');
  $('tg-submit').textContent = 'Simpan Tagihan';
  $('tg-submit').classList.toggle('hidden', mode === 'klaim');
  $('tg-list-title').textContent = mode === 'klaim' ? 'Daftar Klaim BPJS' : 'Daftar Tagihan';
  $('tg-list-hint').textContent = mode === 'klaim' ? 'piutang → dana diterima' : 'terbaru di atas';
  $('tg-filter-wrap').classList.toggle('hidden', mode === 'klaim');
  $('tagihan-list').classList.toggle('hidden', mode === 'klaim');
  $('klaim-wrap').classList.toggle('hidden', mode !== 'klaim');
  // grup yang tersembunyi WAJIB di-disable: elemen display:none tetap ikut
  // validasi `required`, jadi tanpa ini submit selalu diblokir browser
  document.querySelectorAll('#tg-fields-pasien input, #tg-fields-pasien select').forEach((el) => { el.disabled = mode !== 'pasien'; });
  document.querySelectorAll('#tg-fields-klaim input, #tg-fields-klaim select').forEach((el) => { el.disabled = mode !== 'klaim'; });
  if (mode === 'klaim') renderKlaim(); else renderTagihan();
}

document.querySelectorAll('#form-tagihan .seg [data-tg]').forEach((btn) => {
  btn.addEventListener('click', () => setTagihanMode(btn.dataset.tg));
});

// state awal: modul klaim nonaktif supaya tidak ikut validasi form
document.querySelectorAll('#tg-fields-klaim input, #tg-fields-klaim select').forEach((el) => { el.disabled = true; });

// sub-tab Laporan (unit / neraca / modal)
document.querySelectorAll('#view-laporan .seg-tabs [data-lap]').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('#view-laporan .seg-tabs [data-lap]').forEach((b) => b.classList.remove('active'));
    btn.classList.add('active');
    document.querySelectorAll('#view-laporan .subview').forEach((v) => v.classList.remove('active'));
    $('lap-' + btn.dataset.lap).classList.add('active');
    renderLaporanSub(btn.dataset.lap);
  });
});

function renderLaporanSub(name) {
  if (name === 'unit') renderPerUnit();
  if (name === 'neraca') renderNeraca();
  if (name === 'modal') renderModal();
}

// ---------- dashboard ----------
async function renderDashboard() {
  const dari = $('dash-dari').value || '';
  const sampai = $('dash-sampai').value || '';
  const q = new URLSearchParams();
  if (dari) q.set('dari', dari);
  if (sampai) q.set('sampai', sampai);

  // Judul periode & tanggal hari ini (format lokal, bukan UTC)
  $('dash-tanggal').textContent = tanggalPanjang(sampai || todayStr);
  $('dash-periode-label').textContent = rentangPeriode(dari, sampai);

  let d;
  try {
    d = await api('/api/laporan?' + q.toString());
  } catch (e) {
    ['card-dana', 'card-tunai', 'card-bank', 'card-masuk', 'card-keluar',
      'card-piutang', 'card-piutang-pasien', 'card-laba'].forEach((id) => { $(id).textContent = '—'; });
    $('dash-todo').innerHTML = '<p class="empty-state">Data gagal dimuat. Periksa koneksi lalu tekan Muat ulang.</p>';
    return;
  }

  $('card-tunai').textContent = rupiah(d.kas_tunai);
  $('card-bank').textContent = rupiah(d.saldo_bank);
  $('card-masuk').textContent = rupiah(d.masuk);
  $('card-keluar').textContent = rupiah(d.keluar);
  $('card-piutang').textContent = rupiah(d.piutang_bpjs);
  $('card-piutang-pasien').textContent = rupiah(d.piutang_pasien);
  $('card-laba').textContent = rupiah(d.laba_akrual);

  const dana = (Number(d.kas_tunai) || 0) + (Number(d.saldo_bank) || 0);
  $('card-dana').textContent = rupiah(dana);
  $('dash-stamp').textContent = 'per ' + tanggalPendek(sampai || todayStr);

  // Porsi kas tunai vs rekening (dijaga tidak negatif)
  const kasPos = Math.max(0, Number(d.kas_tunai) || 0);
  const bankPos = Math.max(0, Number(d.saldo_bank) || 0);
  const base = kasPos + bankPos;
  const bar = $('dana-bar');
  if (bar.children.length === 2) {
    bar.children[0].style.flex = (base > 0 ? kasPos : 1) + ' 1 0';
    bar.children[1].style.flex = (base > 0 ? bankPos : 1) + ' 1 0';
  }
  bar.setAttribute('aria-label', base > 0
    ? 'Kas tunai ' + Math.round((kasPos / base) * 100) + ' persen, rekening ' + Math.round((bankPos / base) * 100) + ' persen'
    : 'Belum ada saldo');

  const pendapatan = d.pendapatan_akrual != null
    ? d.pendapatan_akrual
    : (d.masuk || 0) - (d.masuk_klaim_bpjs || 0) + (d.bpjs_periode || d.piutang_bpjs_periode || 0) + (d.piutang_pasien_periode || 0);
  const margin = pendapatan > 0 ? Math.round((d.laba_akrual / pendapatan) * 100) : 0;
  const piutangPeriode = (Number(d.bpjs_periode) || 0) + (Number(d.piutang_pasien_periode) || 0);
  $('sub-keluar').textContent = 'keluar dari kas & rekening';
  $('sub-laba').textContent = 'margin ' + margin + '%' + (piutangPeriode > 0 ? ', termasuk piutang ' + shortRp(piutangPeriode) : '');

  const metodeRows = (d.per_metode || []).map((r) => ({
    nama: r.nama, jenis_dana: r.jenis_dana, total: r.total,
  }));
  renderBarList('rekap-utama', d.per_unit, d);
  renderBarList('rekap-sumber', d.per_sumber, d, true);
  renderBarList('rekap-metode', metodeRows, d, true);
  renderBarList('rekap-kategori', d.per_kategori, d, true, true);

  await Promise.all([renderCharts(d), renderRecentTransactions(q), renderTodo()]);
}

// Label tanggal lokal: "Senin, 2 November 2026"
function tanggalPanjang(iso) {
  const dt = parseLokal(iso);
  if (!dt) return '—';
  return dt.toLocaleDateString('id-ID', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
}
function tanggalPendek(iso) {
  const dt = parseLokal(iso);
  if (!dt) return '—';
  return dt.getDate() + ' ' + dt.toLocaleDateString('id-ID', { month: 'short' });
}
function parseLokal(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || ''));
  if (!m) return null;
  return new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
}
function rentangPeriode(dari, sampai) {
  const a = parseLokal(dari), b = parseLokal(sampai);
  if (!a || !b) return '—';
  const opsi = { day: 'numeric', month: 'long', year: 'numeric' };
  if (dari === sampai) return b.toLocaleDateString('id-ID', opsi);
  if (a.getMonth() === b.getMonth() && a.getFullYear() === b.getFullYear()) {
    return a.getDate() + '–' + b.toLocaleDateString('id-ID', opsi);
  }
  return a.toLocaleDateString('id-ID', opsi) + ' – ' + b.toLocaleDateString('id-ID', opsi);
}

// Daftar bar: nama + nilai + porsi bar terhadap nilai terbesar
function renderBarList(elId, rows, d, pakaiJenisDana, modeKeluar) {
  const el = $(elId);
  if (!el) return;
  if (!rows || rows.length === 0) {
    el.innerHTML = '<p class="empty-state">Belum ada data pada periode ini</p>';
    return;
  }
  const max = Math.max(...rows.map((r) => Number(r.total) || 0), 1);
  const total = rows.reduce((s, r) => s + (Number(r.total) || 0), 0);
  el.classList.toggle('out', !!modeKeluar);
  el.innerHTML = rows.map((r) => {
    const v = Number(r.total) || 0;
    const nama = pakaiJenisDana && r.jenis_dana
      ? esc(r.nama) + ' · ' + (r.jenis_dana === 'kas' ? 'tunai' : 'rekening')
      : esc(r.nama);
    const share = total > 0 ? Math.round((v / total) * 100) + '%' : '0%';
    return '<div class="bar-item"><div class="bar-head"><span>' + nama + '</span>' +
      '<span><b class="bar-val">' + rupiah(v) + '</b><span class="bar-share">' + share + '</span></span></div>' +
      '<div class="bar-track"><div class="bar-fill" style="width:' +
      Math.max(2, Math.round((v / max) * 100)) + '%"></div></div></div>';
  }).join('');
}

// Perlu ditindaklanjuti: klaim BPJS diajukan + tagihan pasien belum lunas
async function renderTodo() {
  const box = $('dash-todo');
  const badge = $('todo-count');
  box.innerHTML = '<p class="empty-state">Memuat…</p>';
  let klaim = [], tagihan = [];
  try {
    const hasil = await Promise.all([api('/api/klaim'), api('/api/tagihan')]);
    klaim = hasil[0] || [];
    tagihan = hasil[1] || [];
  } catch (e) {
    box.innerHTML = '<p class="empty-state">Daftar tindak lanjut tidak dapat dimuat. Coba muat ulang.</p>';
    badge.textContent = '0';
    return;
  }
  const piutangKlaim = klaim.filter((k) => k.status !== 'cair');
  const belumLunas = tagihan.filter((t) => (Number(t.sisa) || 0) > 0);
  const total = piutangKlaim.length + belumLunas.length;
  badge.textContent = String(total);
  if (total === 0) {
    box.innerHTML = '<p class="empty-state">Tidak ada yang perlu ditindaklanjuti. Semua klaim cair dan tagihan lunas.</p>';
    return;
  }
  let html = '';
  piutangKlaim.slice(0, 2).forEach((k) => {
    const umur = selisihHari(k.tanggal_ajuan);
    html += '<div class="todo-row"><div class="todo-info">' +
      '<span class="todo-title">Klaim BPJS ' + esc(k.periode || '') + '</span>' +
      '<span class="todo-meta">' + esc(k.sumber || 'BPJS') + (umur != null ? ' · diajukan ' + tanggalPendek(k.tanggal_ajuan) + ', ' + umur + ' hari' : '') + '</span>' +
      '<span class="todo-amount">' + rupiah(k.jumlah) + '</span></div>' +
      '<button type="button" class="btn-outline" onclick="switchView(\'tagihan\')">Tandai cair</button></div>';
  });
  belumLunas.slice(0, 2).forEach((t) => {
    html += '<div class="todo-row"><div class="todo-info">' +
      '<span class="todo-title">Tagihan ' + esc(t.pasien || 'pasien') + '</span>' +
      '<span class="todo-meta">' + esc(t.unit || 'Tagihan') + ' · terbayar ' + rupiah((Number(t.total) || 0) - (Number(t.sisa) || 0)) + ' dari ' + rupiah(t.total) + '</span>' +
      '<span class="todo-amount">Sisa ' + rupiah(t.sisa) + '</span></div>' +
      '<button type="button" class="btn-outline" onclick="switchView(\'tagihan\')">Catat bayar</button></div>';
  });
  const sisa = total - Math.min(2, piutangKlaim.length) - Math.min(2, belumLunas.length);
  if (sisa > 0) {
    const sisaRp = belumLunas.slice(2).reduce((s, t) => s + (Number(t.sisa) || 0), 0)
      + piutangKlaim.slice(2).reduce((s, k) => s + (Number(k.jumlah) || 0), 0);
    html += '<div class="todo-row"><div class="todo-info">' +
      '<span class="todo-title">' + sisa + ' item lain belum selesai</span>' +
      (sisaRp > 0 ? '<span class="todo-amount">Total ' + rupiah(sisaRp) + '</span>' : '') +
      '</div><button type="button" class="btn-outline" onclick="switchView(\'tagihan\')">Lihat semua</button></div>';
  }
  box.innerHTML = html;
}

function selisihHari(iso) {
  const a = parseLokal(iso);
  if (!a) return null;
  const b = parseLokal(todayStr);
  const hari = Math.round((b - a) / 86400000);
  return hari >= 0 ? hari : 0;
}

async function renderRecentTransactions(query) {
  const el = $('dashboard-recent');
  el.innerHTML = '<li class="empty-state">Memuat transaksi…</li>';
  const IN = 'M17 7 7 17M7 8v9h9';
  const OUT = 'M7 17 17 7M8 7h9v9';
  try {
    const rows = await api('/api/transaksi?' + query.toString());
    // Endpoint mengurutkan tanggal DESC, id DESC; jangan tampilkan identitas pasien di ringkasan.
    el.innerHTML = rows.slice(0, 5).map((t) => {
      const masuk = t.jenis === 'masuk';
      const label = masuk ? (t.unit || 'Pemasukan') : (t.kategori || 'Pengeluaran');
      const meta = [
        t.sumber || (masuk ? '' : (t.unit || 'Beban bersama')),
        tanggalPendek(t.tanggal),
        t.dicatat_oleh || '',
      ].filter(Boolean).map(esc).join(' · ');
      return '<li class="tx-row"><span class="tx-icon ' + (masuk ? 'in' : 'out') + '" aria-hidden="true">' +
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="' +
        (masuk ? IN : OUT) + '"/></svg></span>' +
        '<div class="tx-main"><span class="tx-title">' + esc(label) + '</span>' +
        '<span class="tx-meta">' + meta + (t.keterangan ? ' · ' + esc(t.keterangan) : '') + '</span></div>' +
        '<span class="tx-method">' + esc(t.metode || (masuk ? '—' : 'Kas/Rekening')) + '</span>' +
        '<span class="tx-amount ' + (masuk ? 'in' : '') + '">' + (masuk ? '+' : '−') + rupiah(t.jumlah) + '</span></li>';
    }).join('') || '<li class="empty-state">Belum ada transaksi pada periode ini</li>';
  } catch (e) {
    el.innerHTML = '<li class="empty-state">Transaksi belum dapat dimuat. Coba muat ulang.</li>';
  }
}

function renderRekap(elId, rows) {
  const el = $(elId);
  if (!rows || rows.length === 0) {
    el.innerHTML = '<div class="rekap-row empty">Belum ada data</div>';
    return;
  }
  const max = Math.max(...rows.map((r) => r.total), 1);
  el.innerHTML = rows.map((r) => {
    const pct = Math.round((r.total / max) * 100);
    return '<div class="rekap-row"><span class="nama">' + esc(r.nama) + '</span>' +
      '<span class="bar"><span style="width:' + pct + '%"></span></span>' +
      '<span class="total">' + rupiah(r.total) + '</span></div>';
  }).join('');
}

// ---------- grafik (SVG murni, tanpa dependensi) ----------
function shortRp(v) {
  v = Number(v) || 0;
  if (v >= 1e9) return (v / 1e9).toFixed(1).replace('.', ',') + 'M';
  if (v >= 1e6) return (v / 1e6).toFixed(1).replace('.', ',') + 'jt';
  if (v >= 1e3) return Math.round(v / 1e3) + 'rb';
  return String(Math.round(v));
}

function niceMax(v) {
  if (!v || v <= 0) return 1;
  const p = Math.pow(10, Math.floor(Math.log10(v)));
  const m = v / p;
  const f = m <= 1 ? 1 : m <= 2 ? 2 : m <= 2.5 ? 2.5 : m <= 5 ? 5 : 10;
  return f * p;
}

async function renderCharts(d) {
  const sampai = $('dash-sampai').value || todayStr;
  let tren = [];
  try {
    tren = await api('/api/tren?sampai=' + encodeURIComponent(sampai));
  } catch (e) { tren = []; }
  drawArea($('chart-tren'), tren);
  const units = (d.per_unit || []).filter((u) => u.total > 0).slice(0, 6);
  drawDonut($('chart-donut'), $('donut-legend'), units, d.masuk);
}

function drawArea(el, data) {
  if (!el) return;
  if (!data || data.length === 0) {
    el.innerHTML = '<div class="rekap-row empty">Belum ada transaksi</div>';
    return;
  }
  const W = 640, H = 210, PL = 46, PR = 10, PT = 12, PB = 24;
  const n = data.length;
  const max = niceMax(Math.max(1, ...data.map((x) => Math.max(x.masuk, x.keluar))));
  const X = (i) => PL + (n <= 1 ? (W - PL - PR) / 2 : (i * (W - PL - PR)) / (n - 1));
  const Y = (v) => H - PB - (v / max) * (H - PT - PB);
  const path = (k) => data.map((x, i) => (i ? 'L' : 'M') + X(i).toFixed(1) + ',' + Y(x[k]).toFixed(1)).join(' ');
  const area = (k) => path(k) + ' L' + X(n - 1).toFixed(1) + ',' + (H - PB) + ' L' + X(0).toFixed(1) + ',' + (H - PB) + ' Z';

  let grid = '';
  const ticks = 4;
  for (let i = 0; i <= ticks; i++) {
    const v = (max / ticks) * i;
    const y = Y(v).toFixed(1);
    grid += '<line x1="' + PL + '" y1="' + y + '" x2="' + (W - PR) + '" y2="' + y + '"/>';
    grid += '<text x="' + (PL - 8) + '" y="' + (Number(y) + 3.5) + '" text-anchor="end">' + shortRp(v) + '</text>';
  }

  const step = Math.max(1, Math.ceil(n / 6));
  let xlab = '';
  for (let i = 0; i < n; i += step) {
    const t = data[i].tanggal;
    xlab += '<text x="' + X(i).toFixed(1) + '" y="' + (H - 6) + '" text-anchor="middle">' + t.slice(8, 10) + '/' + t.slice(5, 7) + '</text>';
  }

  el.innerHTML =
    '<svg class="chart-svg" viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Arus kas harian">' +
      '<defs>' +
        '<linearGradient id="gm" x1="0" y1="0" x2="0" y2="1">' +
          '<stop offset="0" stop-color="#168779" stop-opacity=".26"/>' +
          '<stop offset="1" stop-color="#168779" stop-opacity="0"/>' +
        '</linearGradient>' +
        '<linearGradient id="gk" x1="0" y1="0" x2="0" y2="1">' +
          '<stop offset="0" stop-color="#e49532" stop-opacity=".22"/>' +
          '<stop offset="1" stop-color="#e49532" stop-opacity="0"/>' +
        '</linearGradient>' +
      '</defs>' +
      '<g class="chart-grid">' + grid + '</g>' +
      '<path d="' + area('masuk') + '" fill="url(#gm)"/>' +
      '<path d="' + area('keluar') + '" fill="url(#gk)"/>' +
      '<path class="ln in" pathLength="1" d="' + path('masuk') + '"/>' +
      '<path class="ln out" pathLength="1" d="' + path('keluar') + '"/>' +
      '<g class="chart-x">' + xlab + '</g>' +
    '</svg>';
}

const DONUT_COLORS = ['#168779', '#4d83c6', '#e49532', '#8b6bb1', '#d03437', '#58a5b3', '#7d8994'];

function drawDonut(el, legendEl, items, total) {
  if (!el) return;
  if (!items || items.length === 0 || total <= 0) {
    el.innerHTML = '<div class="rekap-row empty">Belum ada pemasukan</div>';
    if (legendEl) legendEl.innerHTML = '';
    return;
  }
  const sum = items.reduce((a, b) => a + b.total, 0);
  const R = 62, SW = 24, C = 2 * Math.PI * R;
  let off = 0, segs = '', legend = '';
  items.forEach((it, i) => {
    const frac = sum > 0 ? it.total / sum : 0;
    const len = frac * C;
    const color = DONUT_COLORS[i % DONUT_COLORS.length];
    segs += '<circle class="donut-seg" cx="90" cy="90" r="' + R + '" fill="none" stroke="' + color +
      '" stroke-width="' + SW + '" stroke-dasharray="' + len.toFixed(2) + ' ' + (C - len).toFixed(2) +
      '" stroke-dashoffset="' + (-off).toFixed(2) + '" transform="rotate(-90 90 90)"/>';
    off += len;
    legend += '<div class="dl-row"><span class="dl-dot" style="background:' + color + '"></span>' +
      '<span class="dl-name">' + esc(it.nama) + '</span><b>' + Math.round(frac * 100) + '%</b></div>';
  });
  el.innerHTML = '<svg class="donut-svg" viewBox="0 0 180 180" role="img" aria-label="Komposisi pemasukan per unit">' +
    segs +
    '<text class="donut-total" x="90" y="87" text-anchor="middle">' + shortRp(sum) + '</text>' +
    '<text class="donut-cap" x="90" y="102" text-anchor="middle">TOTAL</text>' +
  '</svg>';
  if (legendEl) legendEl.innerHTML = legend;
}

// ---------- transaksi ----------
// Sumber bayar BPJS = piutang: metode bayar belum berlaku (uangnya belum masuk),
// jadi field metode disembunyikan dan tidak ikut dikirim.
function isBpjsSumber() {
  const el = $('t-sumber');
  if (!el || !el.value) return false;
  const item = MASTER.sumber_bayar.find((s) => String(s.id) === String(el.value));
  return !!(item && item.is_bpjs);
}

function syncBpjsMode() {
  const bpjs = $('t-jenis').value === 'masuk' && isBpjsSumber();
  $('t-bpjs-hint').classList.toggle('hidden', !bpjs);
  $('t-metode-wrap').classList.toggle('hidden', bpjs);
  $('t-metode').disabled = bpjs;
}

$('t-sumber').addEventListener('change', syncBpjsMode);

document.querySelectorAll('#form-transaksi .seg button').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('#form-transaksi .seg button').forEach((b) => b.classList.remove('active'));
    btn.classList.add('active');
    const j = btn.dataset.jenis;
    $('t-jenis').value = j;
    $('masuk-fields').classList.toggle('hidden', j !== 'masuk');
    $('keluar-fields').classList.toggle('hidden', j !== 'keluar');
    syncBpjsMode();
  });
});

$('form-transaksi').addEventListener('submit', async (e) => {
  e.preventDefault();
  const jenis = $('t-jenis').value;
  const bpjs = jenis === 'masuk' && isBpjsSumber();
  const body = {
    tanggal: $('t-tanggal').value,
    jenis,
    jumlah: parseInt($('t-jumlah').value, 10),
    keterangan: $('t-ket').value,
    dicatat_oleh: $('t-oleh').value,
  };
  if (!bpjs) body.metode_bayar_id = parseInt($('t-metode').value, 10);
  if (jenis === 'masuk') {
    body.unit_layanan_id = parseInt($('t-unit').value, 10);
    body.sumber_bayar_id = parseInt($('t-sumber').value, 10);
  } else {
    body.kategori_keluar_id = parseInt($('t-kategori').value, 10);
    const u = $('t-unit-keluar').value;
    body.unit_layanan_id = u ? parseInt(u, 10) : null;
  }
  let res;
  try {
    res = await postJSON('/api/transaksi', body);
  } catch (err) { alert(err.message); return; }
  $('form-transaksi').reset();
  $('t-jenis').value = 'masuk';
  $('t-tanggal').value = todayStr;
  document.querySelectorAll('#form-transaksi .seg button').forEach((b) => b.classList.toggle('active', b.dataset.jenis === 'masuk'));
  $('masuk-fields').classList.remove('hidden');
  $('keluar-fields').classList.add('hidden');
  syncBpjsMode();
  renderTransaksi();
  if (res && res.pencatatan === 'piutang_bpjs') {
    alert('Tercatat sebagai piutang BPJS (bukan kas).\nBuka menu Tagihan → Klaim BPJS saat dana dari BPJS sudah diterima.');
  }
});

async function renderTransaksi() {
  const q = new URLSearchParams();
  if ($('tr-dari').value) q.set('dari', $('tr-dari').value);
  if ($('tr-sampai').value) q.set('sampai', $('tr-sampai').value);
  const rows = await api('/api/transaksi?' + q.toString());
  $('tr-list').innerHTML = rows.map((t) => {
    const desc = t.jenis === 'masuk'
      ? (t.unit || '') + ' · ' + (t.sumber || '')
      : (t.kategori || '') + (t.unit ? ' · ' + t.unit : '');
    const meta = [t.tanggal, t.metode ? 'via ' + t.metode : '', t.pasien ? 'a/n ' + t.pasien : '']
      .filter(Boolean).join(' · ');
    const ket = t.keterangan ? '<div class="li-sub">' + esc(t.keterangan) + ' · ' + esc(t.dicatat_oleh || '') + '</div>' : '';
    return '<li class="' + t.jenis + '"><div class="li-main">' +
      '<div class="li-title">' + esc(desc) + '</div>' +
      '<div class="li-sub">' + esc(meta) + '</div>' + ket + '</div>' +
      '<span class="li-amount">' + (t.jenis === 'masuk' ? '+' : '-') + rupiah(t.jumlah) + '</span>' +
      '<button class="btn-mini hapus" data-del="' + t.id + '">Hapus</button></li>';
  }).join('') || '<li class="rekap-row empty">Belum ada transaksi</li>';

  document.querySelectorAll('#tr-list [data-del]').forEach((b) => {
    b.addEventListener('click', async () => {
      if (!confirm('Hapus transaksi ini?')) return;
      try { await api('/api/transaksi/' + b.dataset.del, { method: 'DELETE' }); } catch (e) { alert(e.message); }
      renderTransaksi();
    });
  });
}

// ---------- tagihan ----------
$('form-tagihan').addEventListener('submit', async (e) => {
  e.preventDefault();
  // Mode klaim tidak punya form: klaim terbentuk dari menu Transaksi.
  if (tgMode === 'klaim') return;

  const body = {
    tanggal: $('tg-tanggal').value,
    nama_pasien: $('tg-pasien').value.trim() || null,
    unit_layanan_id: $('tg-unit').value ? parseInt($('tg-unit').value, 10) : null,
    sumber_bayar_id: $('tg-sumber').value ? parseInt($('tg-sumber').value, 10) : null,
    total: parseInt($('tg-total').value, 10),
    keterangan: $('tg-ket').value.trim() || null,
  };
  try { await postJSON('/api/tagihan', body); } catch (err) { alert(err.message); return; }
  $('tg-pasien').value = '';
  $('tg-total').value = '';
  $('tg-ket').value = '';
  $('tg-tanggal').value = todayStr;
  setTagihanMode('pasien');
});

$('tg-hanya-sisa').addEventListener('change', renderTagihan);

async function renderTagihan() {
  const q = new URLSearchParams();
  if ($('tg-hanya-sisa').checked) q.set('hanya_sisa', 'true');
  const rows = await api('/api/tagihan?' + q.toString());
  $('tagihan-list').innerHTML = rows.map((tg) => {
    const lunas = Number(tg.sisa) <= 0;
    const badge = lunas
      ? '<span class="badge cair">lunas</span>'
      : '<span class="badge diajukan">sisa ' + rupiah(tg.sisa) + '</span>';
    const judul = (tg.nama_pasien || 'Tanpa nama') + (tg.unit ? ' · ' + tg.unit : '');
    const sub = [tg.tanggal, tg.sumber, 'total ' + rupiah(tg.total), 'terbayar ' + rupiah(tg.terbayar)]
      .filter(Boolean).join(' · ');
    const ket = tg.keterangan ? '<div class="li-sub">' + esc(tg.keterangan) + '</div>' : '';
    const payForm = lunas ? '' :
      '<div class="pay-form hidden">' +
        '<div class="pay-row">' +
          '<input type="date" class="pay-tgl" value="' + todayStr + '">' +
          '<select class="pay-metode">' + metodeOptions() + '</select>' +
        '</div>' +
        '<div class="pay-row">' +
          '<input type="number" class="pay-jml" min="1" step="1" placeholder="Jumlah bayar" value="' + tg.sisa + '">' +
          '<button class="btn-mini" data-kirim="' + tg.id + '">Proses</button>' +
        '</div>' +
        '<div class="li-sub">Bisa dipecah: proses sekali untuk tunai, sekali lagi untuk transfer/QRIS.</div>' +
      '</div>';
    return '<li class="' + (lunas ? 'lunas' : '') + '" data-id="' + tg.id + '"><div class="li-main">' +
      '<div class="li-title">' + esc(judul) + '</div>' +
      '<div class="li-sub">' + esc(sub) + '</div>' + ket + '</div>' +
      badge +
      (lunas ? '' : '<button class="btn-mini" data-bayar="' + tg.id + '">Bayar</button>') +
      '<button class="btn-mini hapus" data-deltg="' + tg.id + '">Hapus</button>' +
      payForm + '</li>';
  }).join('') || '<li class="rekap-row empty">Belum ada tagihan</li>';

  document.querySelectorAll('#tagihan-list [data-bayar]').forEach((b) => {
    b.addEventListener('click', () => {
      const pf = b.closest('li').querySelector('.pay-form');
      if (pf) pf.classList.toggle('hidden');
    });
  });

  document.querySelectorAll('#tagihan-list [data-kirim]').forEach((b) => {
    b.addEventListener('click', async () => {
      const li = b.closest('li');
      const body = {
        tanggal: li.querySelector('.pay-tgl').value,
        metode_bayar_id: parseInt(li.querySelector('.pay-metode').value, 10),
        jumlah: parseInt(li.querySelector('.pay-jml').value, 10),
      };
      if (!body.jumlah || body.jumlah <= 0) { alert('Jumlah bayar harus > 0'); return; }
      try { await postJSON('/api/tagihan/' + b.dataset.kirim + '/bayar', body); }
      catch (err) { alert(err.message); return; }
      renderTagihan();
    });
  });

  document.querySelectorAll('#tagihan-list [data-deltg]').forEach((b) => {
    b.addEventListener('click', async () => {
      if (!confirm('Hapus tagihan ini? (pembayaran yang sudah tercatat harus dihapus dulu)')) return;
      try { await api('/api/tagihan/' + b.dataset.deltg, { method: 'DELETE' }); }
      catch (err) { alert(err.message); return; }
      renderTagihan();
    });
  });
}

// ---------- klaim BPJS ----------
// Klaim tidak diinput manual: terbentuk dari pemasukan bersumber BPJS.
// User hanya menekan "Terima Dana" saat uang dari BPJS benar-benar masuk.

async function renderKlaim() {
  const rows = await api('/api/klaim');
  const pending = rows.filter((k) => k.status !== 'cair');
  const cair = rows.filter((k) => k.status === 'cair');
  const totalPending = pending.reduce((a, k) => a + Number(k.jumlah), 0);
  const totalCair = cair.reduce((a, k) => a + Number(k.jumlah), 0);

  $('klaim-list').innerHTML = rows.map((k) => {
    const sudah = k.status === 'cair';
    const badge = sudah
      ? '<span class="badge cair">dana diterima</span>'
      : '<span class="badge diajukan">piutang</span>';
    const ket = k.keterangan ? '<div class="li-sub">' + esc(k.keterangan) + '</div>' : '';
    const meta = [k.tanggal_ajuan + (k.tanggal_cair ? ' → dana diterima ' + k.tanggal_cair : ''),
      k.dicatat_oleh ? 'oleh ' + k.dicatat_oleh : ''].filter(Boolean).join(' · ');
    return '<li class="' + (sudah ? 'lunas' : '') + '" data-id="' + k.id + '"><div class="li-main">' +
      '<div class="li-title">' + esc(k.unit || 'Unit') + (k.sumber ? ' · ' + esc(k.sumber) : '') + '</div>' +
      '<div class="li-sub">' + esc(meta) + '</div>' + ket + '</div>' +
      badge +
      '<span class="li-amount">' + rupiah(k.jumlah) + '</span>' +
      (sudah ? '' : '<button class="btn-mini hapus" data-delk="' + k.id + '">Hapus</button>') +
    '</li>';
  }).join('') || '<li class="rekap-row empty">Belum ada klaim. Catat pemasukan bersumber BPJS di menu Transaksi.</li>';

  // Footer total: baris pertama = jumlah yang masih ditagih ke BPJS (belum diterima).
  $('klaim-total').innerHTML =
    '<div class="kt-row kt-pending"><span>Total ditagih ke BPJS (belum diterima)</span>' +
      '<b>' + rupiah(totalPending) + '</b></div>' +
    (cair.length ? '<div class="kt-row"><span>Sudah diterima (' + cair.length + ' klaim)</span>' +
      '<b>' + rupiah(totalCair) + '</b></div>' : '');

  // Form "Terima Dana" hanya tampil bila ada piutang; kosong saat semua sudah cair.
  // Input yang disembunyikan WAJIB di-disable: display:none tetap ikut validasi required.
  $('tg-klaim-template').classList.toggle('hidden', pending.length === 0);
  document.querySelectorAll('#tg-klaim-template input, #tg-klaim-template select, #kl-submit').forEach((el) => {
    el.disabled = pending.length === 0;
  });
  $('kl-tanggal').value = todayStr;
  $('kl-submit').textContent = 'Terima Dana (' + pending.length + ' klaim · ' + rupiah(totalPending) + ')';

  document.querySelectorAll('#klaim-list [data-delk]').forEach((b) => {
    b.addEventListener('click', async () => {
      if (!confirm('Hapus piutang klaim ini? (belum ada dana diterima)')) return;
      try { await api('/api/klaim/' + b.dataset.delk, { method: 'DELETE' }); } catch (e) { alert(e.message); }
      renderKlaim();
    });
  });
}

$('kl-submit').addEventListener('click', async () => {
  const tanggal = $('kl-tanggal').value;
  const metode = $('kl-metode').value;
  if (!tanggal) { alert('Tanggal terima dana wajib diisi'); return; }
  if (!metode) { alert('Metode bayar wajib dipilih'); return; }
  $('kl-submit').disabled = true;
  try {
    const res = await postJSON('/api/klaim/cair-batch', {
      tanggal_cair: tanggal,
      metode_bayar_id: parseInt(metode, 10),
    });
    alert('Dana diterima: ' + res.jumlah_klaim + ' klaim, total ' + rupiah(res.total) +
      '.\nUang masuk dicatat ke kas/rekening sesuai metode, piutang berkurang.');
  } catch (err) {
    $('kl-submit').disabled = false;
    alert(err.message);
    return;
  }
  renderKlaim();
});

// ---------- laporan per unit ----------
async function renderPerUnit() {
  const q = new URLSearchParams();
  if ($('lu-dari').value) q.set('dari', $('lu-dari').value);
  if ($('lu-sampai').value) q.set('sampai', $('lu-sampai').value);
  const d = await api('/api/laporan-unit?' + q.toString());
  // sembunyikan unit tanpa aktivitas (pendapatan & beban langsung nol) agar tidak berderet kosong
  const aktif = d.units.filter((u) => u.pendapatan_akrual !== 0 || u.beban_langsung !== 0);
  const kosong = aktif.length === 0 && d.total.laba === 0 && d.beban_bersama === 0;
  $('unit-table').innerHTML = kosong
    ? '<div class="rekap-row empty">Belum ada aktivitas pada periode ini</div>'
    : aktif.map((u) => unitCard(u)).join('') + unitCard(d.total, true);
  $('unit-note').textContent = 'Beban bersama ' + rupiah(d.beban_bersama) + ' dialokasikan sesuai proporsi pendapatan tiap unit.';
}

function unitCard(u, total) {
  const margin = u.margin == null ? '—' : u.margin.toFixed(1).replace('.', ',') + '%';
  const nama = total ? 'TOTAL' : (u.nama || '—');
  const labaCls = u.laba >= 0 ? 'pos' : 'neg';
  return '<div class="unit-row' + (total ? ' total' : '') + '">' +
    '<div class="unit-head"><span>' + esc(nama) + '</span><span class="unit-margin">' + margin + '</span></div>' +
    '<div class="unit-sub">Kas ' + rupiah(u.pendapatan_kas) + ' · Piutang BPJS ' + rupiah(u.piutang_bpjs) + ' · Piutang pasien ' + rupiah(u.piutang_pasien) + '</div>' +
    '<div class="unit-grid">' +
      '<div><span>Pendapatan</span><b>' + rupiah(u.pendapatan_akrual) + '</b></div>' +
      '<div><span>Beban langsung</span><b>' + rupiah(u.beban_langsung) + '</b></div>' +
      '<div><span>Beban bersama</span><b>' + rupiah(u.beban_alokasi) + '</b></div>' +
      '<div><span>Laba</span><b class="' + labaCls + '">' + rupiah(u.laba) + '</b></div>' +
    '</div>' +
  '</div>';
}

// ---------- neraca ----------
async function renderNeraca() {
  const q = new URLSearchParams();
  if ($('nc-per').value) q.set('per', $('nc-per').value);
  const d = await api('/api/neraca?' + q.toString());
  const A = d.aset, E = d.ekuitas;
  const row = (k, v, strong) => '<div class="kv-row' + (strong ? ' strong' : '') + '"><span>' + k + '</span><b>' + v + '</b></div>';
  $('neraca-body').innerHTML =
    '<div class="neraca-col"><h3>Aset</h3>' +
      row('Kas tunai', rupiah(A.kas_tunai)) +
      row('Saldo rekening', rupiah(A.saldo_bank)) +
      row('Piutang BPJS', rupiah(A.piutang_bpjs)) +
      row('Piutang pasien', rupiah(A.piutang_pasien)) +
      row('Total aset', rupiah(A.total), true) +
    '</div>' +
    '<div class="neraca-col"><h3>Ekuitas</h3>' +
      row('Modal', rupiah(E.modal)) +
      row('Laba berjalan', rupiah(E.laba_berjalan)) +
      row('Total ekuitas', rupiah(E.total), true) +
    '</div>' +
    '<div class="hint">' + (d.seimbang
      ? 'Seimbang: aset = ekuitas.'
      : 'BELUM seimbang: aset ' + rupiah(A.total) + ' vs ekuitas ' + rupiah(E.total) + '.') + '</div>';
}

// ---------- modal ----------
document.querySelectorAll('#form-modal .seg [data-mjenis]').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('#form-modal .seg [data-mjenis]').forEach((b) => b.classList.remove('active'));
    btn.classList.add('active');
    $('m-jenis').value = btn.dataset.mjenis;
  });
});

$('form-modal').addEventListener('submit', async (e) => {
  e.preventDefault();
  try {
    await postJSON('/api/modal', {
      tanggal: $('m-tanggal').value,
      jenis: $('m-jenis').value,
      jenis_dana: $('m-dana').value,
      jumlah: parseInt($('m-jumlah').value, 10),
      keterangan: $('m-ket').value.trim() || null,
    });
  } catch (err) { alert(err.message); return; }
  $('form-modal').reset();
  $('m-jenis').value = 'saldo_awal';
  $('m-tanggal').value = todayStr;
  document.querySelectorAll('#form-modal .seg [data-mjenis]').forEach((b) => b.classList.toggle('active', b.dataset.mjenis === 'saldo_awal'));
  renderModal();
});

async function renderModal() {
  const rows = await api('/api/modal');
  const label = { saldo_awal: 'Saldo awal', setoran: 'Setoran modal', prive: 'Prive' };
  const dana = { kas: 'Kas tunai', bank: 'Rekening' };
  $('modal-list').innerHTML = rows.map((m) => {
    const sign = m.jenis === 'prive' ? '-' : '+';
    const cls = m.jenis === 'prive' ? 'keluar' : 'masuk';
    return '<li class="' + cls + '"><div class="li-main">' +
      '<div class="li-title">' + label[m.jenis] + ' · ' + dana[m.jenis_dana] + '</div>' +
      '<div class="li-sub">' + m.tanggal + (m.keterangan ? ' · ' + esc(m.keterangan) : '') + '</div></div>' +
      '<span class="li-amount">' + sign + rupiah(m.jumlah) + '</span>' +
      '<button class="btn-mini hapus" data-delm="' + m.id + '">Hapus</button></li>';
  }).join('') || '<li class="rekap-row empty">Belum ada data modal</li>';

  document.querySelectorAll('#modal-list [data-delm]').forEach((b) => {
    b.addEventListener('click', async () => {
      if (!confirm('Hapus data modal ini?')) return;
      try { await api('/api/modal/' + b.dataset.delm, { method: 'DELETE' }); } catch (e) { alert(e.message); }
      renderModal();
    });
  });
}

// ---------- pasien & nakes (Tahap 2) ----------
let psMode = 'pasien';
let editingPasienId = null;

function setPsMode(mode) {
  psMode = mode;
  document.querySelectorAll('#view-pasien .seg [data-ps]').forEach((b) => b.classList.toggle('active', b.dataset.ps === mode));
  $('form-pasien').classList.toggle('hidden', mode !== 'pasien');
  $('form-nakes').classList.toggle('hidden', mode !== 'nakes');
  $('pasien-list').classList.toggle('hidden', mode !== 'pasien');
  $('nakes-list').classList.toggle('hidden', mode !== 'nakes');
  $('ps-search-wrap').classList.toggle('hidden', mode !== 'pasien');
  $('ps-list-title').textContent = mode === 'pasien' ? 'Daftar Pasien' : 'Daftar Nakes';
  $('ps-list-hint').textContent = mode === 'pasien' ? 'terbaru di atas' : 'tenaga kesehatan';
  if (mode === 'pasien') renderPasien(); else renderNakes();
}

document.querySelectorAll('#view-pasien .seg [data-ps]').forEach((btn) => {
  btn.addEventListener('click', () => setPsMode(btn.dataset.ps));
});

function resetPasienForm() {
  editingPasienId = null;
  $('form-pasien').reset();
  $('p-submit').textContent = 'Simpan Pasien';
}

$('form-pasien').addEventListener('submit', async (e) => {
  e.preventDefault();
  const body = {
    no_rm: $('p-no-rm').value.trim() || null,
    nama: $('p-nama').value.trim(),
    nik: $('p-nik').value.trim() || null,
    no_bpjs: $('p-bpjs').value.trim() || null,
    tanggal_lahir: $('p-tgl-lahir').value || null,
    jenis_kelamin: $('p-jk').value || null,
    alamat: $('p-alamat').value.trim() || null,
    no_telepon: $('p-telp').value.trim() || null,
  };
  if (!body.nama) { alert('Nama wajib diisi'); return; }
  try {
    if (editingPasienId) await postJSON('/api/pasien/' + editingPasienId, body, 'PUT');
    else await postJSON('/api/pasien', body);
  } catch (err) { alert(err.message); return; }
  resetPasienForm();
  renderPasien();
});

async function renderPasien() {
  const cari = $('ps-cari').value.trim();
  const q = cari ? '?cari=' + encodeURIComponent(cari) : '';
  const rows = await api('/api/pasien' + q);
  $('pasien-list').innerHTML = rows.map((p) => {
    const meta = [
      p.no_rm ? 'No. RM ' + esc(p.no_rm) : '',
      p.jenis_kelamin ? (p.jenis_kelamin === 'L' ? 'Laki-laki' : 'Perempuan') : '',
      p.tanggal_lahir ? 'lahir ' + p.tanggal_lahir : '',
      p.no_bpjs ? 'BPJS ' + esc(p.no_bpjs) : '',
      p.nik ? 'NIK ' + esc(p.nik) : '',
      p.no_telepon ? esc(p.no_telepon) : '',
    ].filter(Boolean).join(' · ');
    const sub = p.alamat ? '<div class="li-sub">' + esc(p.alamat) + '</div>' : '';
    return '<li><div class="li-main">' +
      '<div class="li-title">' + esc(p.nama) + '</div>' +
      '<div class="li-sub">' + meta + '</div>' + sub + '</div>' +
      '<button class="btn-mini" data-edit="' + p.id + '">Edit</button>' +
      '<button class="btn-mini hapus" data-del="' + p.id + '">Hapus</button></li>';
  }).join('') || '<li class="rekap-row empty">Belum ada pasien</li>';

  document.querySelectorAll('#pasien-list [data-edit]').forEach((b) => {
    b.addEventListener('click', () => {
      const id = b.dataset.edit;
      const p = rows.find((x) => String(x.id) === String(id));
      if (!p) return;
      editingPasienId = p.id;
      $('p-no-rm').value = p.no_rm || '';
      $('p-nama').value = p.nama || '';
      $('p-nik').value = p.nik || '';
      $('p-bpjs').value = p.no_bpjs || '';
      $('p-tgl-lahir').value = p.tanggal_lahir || '';
      $('p-jk').value = p.jenis_kelamin || '';
      $('p-alamat').value = p.alamat || '';
      $('p-telp').value = p.no_telepon || '';
      $('p-submit').textContent = 'Simpan Perubahan';
      $('form-pasien').scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });

  document.querySelectorAll('#pasien-list [data-del]').forEach((b) => {
    b.addEventListener('click', async () => {
      if (!confirm('Hapus pasien ini?')) return;
      try { await api('/api/pasien/' + b.dataset.del, { method: 'DELETE' }); } catch (e) { alert(e.message); }
      renderPasien();
    });
  });
}

$('form-nakes').addEventListener('submit', async (e) => {
  e.preventDefault();
  const body = {
    nama: $('n-nama').value.trim(),
    profesi: $('n-profesi').value.trim() || null,
    sip: $('n-sip').value.trim() || null,
    status: $('n-status').value,
  };
  if (!body.nama) { alert('Nama wajib diisi'); return; }
  try { await postJSON('/api/nakes', body); } catch (err) { alert(err.message); return; }
  $('form-nakes').reset();
  renderNakes();
});

async function renderNakes() {
  const rows = await api('/api/nakes');
  $('nakes-list').innerHTML = rows.map((n) => {
    const meta = [n.profesi, n.sip ? 'SIP ' + esc(n.sip) : ''].filter(Boolean).join(' · ');
    const badge = n.status === 'nonaktif'
      ? '<span class="badge diajukan">nonaktif</span>'
      : '<span class="badge cair">aktif</span>';
    return '<li><div class="li-main">' +
      '<div class="li-title">' + esc(n.nama) + '</div>' +
      '<div class="li-sub">' + meta + '</div></div>' +
      badge +
      '<button class="btn-mini" data-edit="' + n.id + '">Edit</button>' +
      '<button class="btn-mini hapus" data-del="' + n.id + '">Hapus</button></li>';
  }).join('') || '<li class="rekap-row empty">Belum ada nakes</li>';

  document.querySelectorAll('#nakes-list [data-edit]').forEach((b) => {
    b.addEventListener('click', async () => {
      const id = b.dataset.edit;
      const n = rows.find((x) => String(x.id) === String(id));
      if (!n) return;
      const nama = prompt('Nama:', n.nama || '');
      if (!nama) return;
      const profesi = prompt('Profesi:', n.profesi || '') || '';
      const sip = prompt('SIP / STR:', n.sip || '') || '';
      try {
        await postJSON('/api/nakes/' + id, {
          nama, profesi: profesi || null, sip: sip || null, status: n.status,
        }, 'PUT');
      } catch (e) { alert(e.message); }
      renderNakes();
    });
  });

  document.querySelectorAll('#nakes-list [data-del]').forEach((b) => {
    b.addEventListener('click', async () => {
      if (!confirm('Hapus nakes ini?')) return;
      try { await api('/api/nakes/' + b.dataset.del, { method: 'DELETE' }); } catch (e) { alert(e.message); }
      renderNakes();
    });
  });
}

$('ps-cari').addEventListener('input', () => {
  clearTimeout($('ps-cari')._t);
  $('ps-cari')._t = setTimeout(renderPasien, 300);
});

// ---------- kunjungan & rekam medis (Tahap 3) ----------
let rmKunjunganId = null;

async function loadKunjunganOptions() {
  await fillSelectAsync('kj-pasien', '/api/pasien');
  await fillSelectAsync('kj-unit', '/api/master');
  await fillSelectAsync('kj-sumber', '/api/master');
  await fillSelectAsync('kj-nakes', '/api/nakes');
}

async function fillSelectAsync(id, url) {
  const el = $(id);
  if (!el) return;
  el.innerHTML = '';
  try {
    let items;
    if (url === '/api/master') {
      const m = await api(url);
      items = id === 'kj-unit' ? m.unit_layanan : m.sumber_bayar;
    } else if (url === '/api/nakes') {
      items = (await api(url)).filter((n) => n.status === 'aktif');
    } else {
      items = await api(url);
    }
    el.innerHTML = '<option value="">—</option>' + items.map((it) => {
      const label = id === 'kj-pasien'
        ? it.nama + (it.no_rm ? ' · ' + it.no_rm : '')
        : it.nama;
      return '<option value="' + it.id + '">' + esc(label) + '</option>';
    }).join('');
  } catch (e) { /* daftar kosong, biarkan '—' */ }
}

const STATUS_LABEL = { menunggu: 'Menunggu', diperiksa: 'Diperiksa', selesai: 'Selesai', batal: 'Batal' };

async function renderKunjungan() {
  await loadKunjunganOptions();
  const tanggal = $('kj-filter').value;
  const q = tanggal ? '?tanggal=' + encodeURIComponent(tanggal) : '';
  const rows = await api('/api/kunjungan' + q);
  $('kj-list').innerHTML = rows.map((k) => {
    const meta = [
      'No. ' + esc(k.no_antrian),
      k.pasien_nama ? esc(k.pasien_nama) : '',
      k.no_rm ? esc(k.no_rm) : '',
      k.unit ? esc(k.unit) : '',
      k.nakes_nama ? esc(k.nakes_nama) : '',
      k.sumber ? esc(k.sumber) : '',
      k.keluhan ? esc(k.keluhan) : '',
    ].filter(Boolean).join(' · ');
    const actions = [
      k.status === 'menunggu' ? '<button class="btn-mini" data-stat="diperiksa" data-id="' + k.id + '">Periksa</button>' : '',
      (k.status === 'menunggu' || k.status === 'diperiksa') ? '<button class="btn-mini" data-stat="selesai" data-id="' + k.id + '">Selesai</button>' : '',
      (k.status === 'menunggu') ? '<button class="btn-mini hapus" data-stat="batal" data-id="' + k.id + '">Batal</button>' : '',
      '<button class="btn-mini" data-rm="' + k.id + '" title="Rekam medis">RM</button>',
      '<button class="btn-mini hapus" data-del="' + k.id + '">Hapus</button>',
    ].join('');
    return '<li class="' + k.status + '"><div class="li-main">' +
      '<div class="li-title">' + esc(k.pasien_nama || '') + '</div>' +
      '<div class="li-sub">' + meta + '</div></div>' +
      '<span class="badge ' + k.status + '">' + (STATUS_LABEL[k.status] || k.status) + '</span>' +
      (k.ada_rekam ? '<span class="badge cair" title="ada rekam medis">RM</span>' : '') +
      '<div class="row-actions">' + actions + '</div></li>';
  }).join('') || '<li class="rekap-row empty">Belum ada kunjungan</li>';

  $('kj-list').querySelectorAll('[data-stat]').forEach((b) => {
    b.addEventListener('click', async () => {
      try { await postJSON('/api/kunjungan/' + b.dataset.id + '/status', { status: b.dataset.stat }); }
      catch (e) { alert(e.message); }
      renderKunjungan();
    });
  });
  $('kj-list').querySelectorAll('[data-del]').forEach((b) => {
    b.addEventListener('click', async () => {
      if (!confirm('Hapus kunjungan ini? (rekam medis ikut terhapus)')) return;
      try { await api('/api/kunjungan/' + b.dataset.del, { method: 'DELETE' }); } catch (e) { alert(e.message); }
      renderKunjungan();
    });
  });
  $('kj-list').querySelectorAll('[data-rm]').forEach((b) => {
    b.addEventListener('click', () => openRekamMedis(b.dataset.rm));
  });
}

async function openRekamMedis(kid) {
  rmKunjunganId = kid;
  $('rm-title').textContent = 'Rekam Medis — Kunjungan #' + kid;
  $('rm-anamnesa').value = '';
  $('rm-diagnosa').value = '';
  $('rm-tindakan').value = '';
  $('rm-terapi').value = '';
  $('rm-keterangan').value = '';
  try {
    const rm = await api('/api/rekam-medis/' + kid);
    if (rm) {
      $('rm-anamnesa').value = rm.anamnesa || '';
      $('rm-diagnosa').value = rm.diagnosa || '';
      $('rm-tindakan').value = rm.tindakan || '';
      $('rm-terapi').value = rm.terapi || '';
      $('rm-keterangan').value = rm.keterangan || '';
    }
  } catch (e) { /* kosong */ }
  $('modal-rekam').classList.remove('hidden');
}

$('form-kunjungan').addEventListener('submit', async (e) => {
  e.preventDefault();
  const body = {
    tanggal: $('kj-tanggal').value,
    pasien_id: parseInt($('kj-pasien').value, 10),
    unit_layanan_id: parseInt($('kj-unit').value, 10) || null,
    nakes_id: parseInt($('kj-nakes').value, 10) || null,
    sumber_bayar_id: parseInt($('kj-sumber').value, 10) || null,
    keluhan: $('kj-keluhan').value.trim() || null,
  };
  if (!body.tanggal) { alert('Tanggal wajib diisi'); return; }
  if (!body.pasien_id) { alert('Pilih pasien'); return; }
  try {
    const r = await postJSON('/api/kunjungan', body);
    $('form-kunjungan').reset();
    $('kj-tanggal').value = todayStr;
    $('kj-filter').value = todayStr;
    alert('Kunjungan terdaftar — No. Antrian ' + r.no_antrian);
  } catch (err) { alert(err.message); return; }
  renderKunjungan();
});

$('kj-filter').addEventListener('change', renderKunjungan);

$('form-rekam').addEventListener('submit', async (e) => {
  e.preventDefault();
  if (!rmKunjunganId) return;
  const body = {
    kunjungan_id: rmKunjunganId,
    // Kirim string apa adanya (bukan null): field yang DIKOSONGKAN dokter
    // harus benar-benar terhapus, sedangkan field yang tidak dikirim (null)
    // dipertahankan backend.
    anamnesa: $('rm-anamnesa').value.trim(),
    diagnosa: $('rm-diagnosa').value.trim(),
    tindakan: $('rm-tindakan').value.trim(),
    terapi: $('rm-terapi').value.trim(),
    keterangan: $('rm-keterangan').value.trim(),
  };
  try { await postJSON('/api/rekam-medis', body); }
  catch (err) { alert(err.message); return; }
  $('modal-rekam').classList.add('hidden');
  renderKunjungan();
});

$('rm-batal').addEventListener('click', () => $('modal-rekam').classList.add('hidden'));

// ---------- master ----------
function renderMaster() {
  const blocks = [
    { key: 'unit_layanan', title: 'Unit Layanan', tipe: 'unit_layanan' },
    { key: 'sumber_bayar', title: 'Sumber Bayar', tipe: 'sumber_bayar' },
    { key: 'kategori_keluar', title: 'Kategori Pengeluaran', tipe: 'kategori_keluar' },
    { key: 'metode_bayar', title: 'Metode Bayar', tipe: 'metode_bayar', metode: true },
  ];
  $('master-sections').innerHTML = blocks.map((b) => {
    const rows = MASTER[b.key].map((it) => {
      const label = b.metode
        ? esc(it.nama) + ' <span class="dana-tag">' + (it.jenis_dana === 'kas' ? 'tunai' : 'rekening') + '</span>'
        : esc(it.nama);
      return '<div class="master-row" data-id="' + it.id + '">' +
        '<span class="master-nama">' + label + '</span>' +
        '<span class="master-actions">' +
          '<button class="btn-mini" data-edit="1">Edit</button>' +
          '<button class="btn-mini hapus" data-del="1">Hapus</button>' +
        '</span>' +
      '</div>';
    }).join('');
    const addForm = b.metode
      ? '<div class="master-add"><input id="add-' + b.tipe + '" placeholder="Nama metode">' +
        '<select id="dana-' + b.tipe + '"><option value="kas">tunai</option><option value="bank">rekening</option></select>' +
        '<button data-tipe="' + b.tipe + '">Tambah</button></div>'
      : '<div class="master-add"><input id="add-' + b.tipe + '" placeholder="Tambah ' + b.title.toLowerCase() + '"><button data-tipe="' + b.tipe + '">Tambah</button></div>';
    return '<div class="master-block" data-tipe="' + b.tipe + '"><h3>' + b.title + '</h3>' + rows + addForm + '</div>';
  }).join('');

  document.querySelectorAll('.master-add button').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const tipe = btn.dataset.tipe;
      const input = $('add-' + tipe);
      const nama = input.value.trim();
      if (!nama) return;
      try {
        if (tipe === 'metode_bayar') {
          await postJSON('/api/metode', { nama, jenis_dana: $('dana-' + tipe).value });
        } else {
          await postJSON('/api/master/' + tipe, { nama });
        }
      } catch (e) { alert(e.message); }
      await loadMaster();
    });
  });

  document.querySelectorAll('.master-row [data-del]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const row = btn.closest('.master-row');
      const tipe = row.closest('.master-block').dataset.tipe;
      const id = row.dataset.id;
      if (!confirm('Hapus data ini?')) return;
      try {
        const path = tipe === 'metode_bayar' ? '/api/metode/' + id : '/api/master/' + tipe + '/' + id;
        await api(path, { method: 'DELETE' });
      } catch (e) { alert(e.message); }
      await loadMaster();
    });
  });

  document.querySelectorAll('.master-row [data-edit]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const row = btn.closest('.master-row');
      const block = row.closest('.master-block');
      const tipe = block.dataset.tipe;
      const id = row.dataset.id;
      const isMetode = tipe === 'metode_bayar';
      const item = (MASTER[tipe] || []).find((x) => String(x.id) === String(id));
      const nama = isMetode ? (item ? item.nama : '') : row.querySelector('.master-nama').textContent;
      const dana = isMetode && item ? item.jenis_dana : 'kas';
      row.innerHTML =
        '<input class="master-edit-input" value="' + esc(nama) + '">' +
        (isMetode ? '<select class="master-edit-dana"><option value="kas"' + (dana === 'kas' ? ' selected' : '') + '>tunai</option><option value="bank"' + (dana === 'bank' ? ' selected' : '') + '>rekening</option></select>' : '') +
        '<span class="master-actions">' +
          '<button class="btn-mini" data-save="1">Simpan</button>' +
          '<button class="btn-mini" data-cancel="1">Batal</button>' +
        '</span>';
      row.querySelector('[data-save]').addEventListener('click', async () => {
        const val = row.querySelector('.master-edit-input').value.trim();
        if (!val) return;
        try {
          if (isMetode) {
            await postJSON('/api/metode/' + id, { nama: val, jenis_dana: row.querySelector('.master-edit-dana').value }, 'PUT');
          } else {
            await postJSON('/api/master/' + tipe + '/' + id, { nama: val }, 'PUT');
          }
        } catch (e) { alert(e.message); }
        await loadMaster();
      });
      row.querySelector('[data-cancel]').addEventListener('click', () => loadMaster());
    });
  });
}

// ---------- util ----------
function esc(s) {
  return String(s || '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

// ---------- events for filters ----------
$('dash-dari').value = monthStart;
$('dash-sampai').value = todayStr;
$('tr-dari').value = monthStart;
$('tr-sampai').value = todayStr;
$('t-tanggal').value = todayStr;
$('tg-tanggal').value = todayStr;
$('m-tanggal').value = todayStr;
$('lu-dari').value = monthStart;
$('lu-sampai').value = todayStr;
$('nc-per').value = todayStr;
$('kj-tanggal').value = todayStr;
$('kj-filter').value = todayStr;

['dash-dari', 'dash-sampai'].forEach((id) => $(id).addEventListener('change', () => {
  setPeriodeAktif('kustom');
  renderDashboard();
}));

// Periode cepat: Hari ini / Bulan ini / Kustom
function setPeriodeAktif(mode) {
  document.querySelectorAll('.seg-period [data-periode]').forEach((b) => {
    const on = b.dataset.periode === mode;
    b.classList.toggle('active', on);
    b.setAttribute('aria-pressed', on ? 'true' : 'false');
  });
}
document.querySelectorAll('.seg-period [data-periode]').forEach((b) => {
  b.addEventListener('click', () => {
    const mode = b.dataset.periode;
    setPeriodeAktif(mode);
    if (mode === 'hari') { $('dash-dari').value = todayStr; $('dash-sampai').value = todayStr; }
    if (mode === 'bulan') { $('dash-dari').value = monthStart; $('dash-sampai').value = todayStr; }
    if (mode === 'kustom') { const el = $('dash-dari'); if (el && el.focus) el.focus(); return; }
    renderDashboard();
  });
});

// Tab pengelompokan pemasukan: Unit layanan / Sumber bayar / Metode bayar
document.querySelectorAll('[data-rekap]').forEach((b) => {
  b.addEventListener('click', () => {
    document.querySelectorAll('[data-rekap]').forEach((x) => {
      const on = x === b;
      x.classList.toggle('active', on);
      x.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    const map = { unit: 'rekap-utama', sumber: 'rekap-sumber', metode: 'rekap-metode' };
    Object.entries(map).forEach(([k, id]) => {
      const el = $(id);
      if (el) el.classList.toggle('hidden', k !== b.dataset.rekap);
    });
  });
});
['tr-dari', 'tr-sampai'].forEach((id) => $(id).addEventListener('change', renderTransaksi));
['lu-dari', 'lu-sampai'].forEach((id) => $(id).addEventListener('change', renderPerUnit));
$('nc-per').addEventListener('change', renderNeraca);
$('dash-refresh').addEventListener('click', renderDashboard);

// ---------- refresh real-time ----------
setInterval(() => { if (currentView === 'dashboard' && CURRENT_USER) renderDashboard(); }, 20000);
document.addEventListener('visibilitychange', () => {
  if (!document.hidden && currentView === 'dashboard' && CURRENT_USER) renderDashboard();
});

// ---------- auth: login, logout, ganti password, kelola user ----------
function renderNavUser() {
  if (!CURRENT_USER) return;
  const name = CURRENT_USER.nama || CURRENT_USER.username;
  $('nav-username').textContent = name;
  $('nav-avatar').textContent = (name[0] || 'F').toUpperCase();
  if (CURRENT_USER.role === 'admin') $('nav-username').title = 'Admin';
}

$('form-login').addEventListener('submit', async (e) => {
  e.preventDefault();
  const err = $('login-err');
  err.textContent = '';
  const username = $('login-username').value.trim();
  const password = $('login-password').value;
  try {
    const res = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { err.textContent = data.detail || 'Gagal masuk'; return; }
    AUTH_TOKEN = data.token;
    localStorage.setItem('kfm_token', data.token);
    CURRENT_USER = data.user;
    renderNavUser();
    hideLogin();
    $('login-password').value = '';
    await loadMaster();
    switchView(currentView);
  } catch (ex) {
    err.textContent = ex.message;
  }
});

$('btn-logout').addEventListener('click', async () => {
  try { await api('/api/logout', { method: 'POST' }); } catch (_) {}
  AUTH_TOKEN = '';
  localStorage.removeItem('kfm_token');
  CURRENT_USER = null;
  showLogin();
});

$('btn-ganti-pass').addEventListener('click', () => {
  $('pw-lama').value = '';
  $('pw-baru').value = '';
  $('pw-err').textContent = '';
  $('modal-password').classList.remove('hidden');
});
$('pw-batal').addEventListener('click', () => $('modal-password').classList.add('hidden'));
$('form-password').addEventListener('submit', async (e) => {
  e.preventDefault();
  const err = $('pw-err');
  err.textContent = '';
  try {
    await api('/api/ganti-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password_lama: $('pw-lama').value, password_baru: $('pw-baru').value }),
    });
    $('modal-password').classList.add('hidden');
    alert('Password berhasil diganti.');
  } catch (ex) {
    err.textContent = ex.message;
  }
});

async function renderUsers() {
  const box = $('user-sections');
  if (!box) return;
  if (!CURRENT_USER || CURRENT_USER.role !== 'admin') { box.innerHTML = ''; return; }
  let users;
  try { users = await api('/api/users'); } catch (_) { return; }
  const isSelf = (u) => CURRENT_USER && u.id === CURRENT_USER.id;
  box.innerHTML = `
    <div class="card">
      <div class="card-head"><h2>Pengguna &amp; Hak Akses</h2><span class="tag muted">khusus admin</span></div>
      <table class="tbl">
        <thead><tr><th>Username</th><th>Nama</th><th>Peran</th><th></th></tr></thead>
        <tbody>
          ${users.map((u) => `
            <tr>
              <td>${u.username}${isSelf(u) ? ' <span class="tag muted">Anda</span>' : ''}</td>
              <td>${u.nama || '-'}</td>
              <td><span class="tag ${u.role === 'admin' ? 'tag-danger' : ''}">${u.role}</span></td>
              <td class="row-actions">
                ${!isSelf(u) ? `<button class="btn-mini danger" onclick="delUser(${u.id})">Hapus</button>` : ''}
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table>
      <div class="card-sub">
        <h3>Tambah pengguna</h3>
        <div class="form" style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;align-items:end">
          <label>Username<input type="text" id="nu-user" placeholder="petugas1"></label>
          <label>Nama<input type="text" id="nu-nama" placeholder="Nama lengkap"></label>
          <label>Peran
            <select id="nu-role"><option value="petugas">petugas</option><option value="admin">admin</option></select>
          </label>
          <label>Password<input type="text" id="nu-pass" placeholder="min. 6 karakter"></label>
        </div>
        <button class="btn-primary" id="nu-save" style="margin-top:10px">Tambah Pengguna</button>
      </div>
    </div>`;
  $('nu-save').addEventListener('click', async () => {
    try {
      await api('/api/users', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: $('nu-user').value, nama: $('nu-nama').value,
          role: $('nu-role').value, password: $('nu-pass').value,
        }),
      });
      renderUsers();
    } catch (ex) { alert(ex.message); }
  });
}
async function delUser(id) {
  if (!confirm('Hapus pengguna ini? Sesi mereka juga akan diakhiri.')) return;
  try { await api('/api/users/' + id, { method: 'DELETE' }); renderUsers(); }
  catch (ex) { alert(ex.message); }
}

// ---------- start ----------
async function bootstrap() {
  if (!AUTH_TOKEN) { showLogin(); return; }
  try {
    CURRENT_USER = await api('/api/me');
    renderNavUser();
    hideLogin();
    await loadMaster();
    switchView(currentView);
  } catch (_) {
    showLogin();
  }
}
bootstrap();
