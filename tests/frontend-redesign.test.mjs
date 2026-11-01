import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
const root = new URL('../', import.meta.url);
const file = name => readFileSync(new URL('src/klinik_famitra_app/static/' + name, root), 'utf8');

test('brand dashboard provides an accessible seven-view rail and asymmetric clinic panels without losing existing IDs', () => {
  const html = file('index.html');
  const original = execFileSync('git', ['show', 'HEAD:src/klinik_famitra_app/static/index.html'], { cwd: root, encoding: 'utf8' });
  const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map(m => m[1]);
  // Input klaim manual sengaja DIHAPUS: klaim BPJS kini terbentuk otomatis dari
  // pemasukan bersumber BPJS, jadi tidak ada lagi form klaim untuk diisi.
  const removed = new Set(['k-tanggal', 'k-unit', 'k-jumlah', 'k-ket']);
  for (const match of original.matchAll(/\bid="([^"]+)"/g)) {
    if (removed.has(match[1])) continue;
    assert.ok(ids.includes(match[1]), 'preserve ' + match[1]);
  }
  for (const id of removed) assert.ok(!ids.includes(id), 'manual claim input removed: ' + id);
  assert.equal(new Set(ids).size, ids.length, 'IDs must remain unique');
  assert.match(html, /class="dashboard-workspace"/);
  assert.match(html, /class="[^"\n]*account-summary/);
  const rail = html.match(/<nav class="sidebar[\s\S]*?<\/nav>/)?.[0];
  assert.ok(rail, 'icon rail is present');
  for (const view of ['dashboard', 'transaksi', 'tagihan', 'pasien', 'kunjungan', 'laporan', 'master']) {
    assert.match(rail, new RegExp('data-view="' + view + '"'));
  }
  assert.match(rail, /aria-label="Navigasi utama"/);
  assert.equal((rail.match(/<svg/g) || []).length, 7);
  assert.match(file('style.css'), /--brand:\s*#d03437/);
  assert.match(file('style.css'), /--text:\s*#363533/);
});


test('mobile navigation keeps seven modules behind five buttons and a keyboard-safe More dialog', () => {
  const html = file('index.html');
  const nav = html.match(/<nav class="tabbar"[\s\S]*?<\/nav>/)[0];
  assert.equal((nav.match(/<button/g) || []).length, 5);
  assert.match(nav, /class="mobile-create"[^>]*data-view="transaksi"/);
  assert.match(nav, /aria-controls="mobile-more"[^>]*aria-expanded="false"/);
  const dialog = html.match(/<dialog id="mobile-more"[\s\S]*?<\/dialog>/)?.[0];
  assert.ok(dialog, 'More uses native modal focus containment and Escape dismissal');
  assert.deepEqual([...nav.matchAll(/data-view="([^"]+)"/g)].map(m => m[1]), ['dashboard', 'tagihan', 'transaksi', 'laporan']);
  assert.deepEqual([...dialog.matchAll(/data-view="([^"]+)"/g)].map(m => m[1]), ['pasien', 'kunjungan', 'master']);
  const elements = new Map();
  const get = id => {
    if (!elements.has(id)) elements.set(id, {
      open: false, attrs: {}, events: {}, dataset: {},
      classList: { add() {}, remove() {}, toggle() {} },
      setAttribute(k, v) { this.attrs[k] = v; }, removeAttribute(k) { delete this.attrs[k]; },
      addEventListener(k, fn) { this.events[k] = fn; },
      focus() { this.focused = true; },
      showModal() { this.open = true; },
      close() { this.open = false; this.events.close?.(); },
    });
    return elements.get(id);
  };
  const nodes = ['dashboard', 'pasien', 'transaksi', 'kunjungan', 'tagihan', 'laporan', 'master'].map(view => {
    const node = get('nav-' + view); node.dataset.view = view; return node;
  });
  let rendered;
  const context = vm.createContext({ $: get, document: { querySelectorAll: s => s === '[data-view]' ? nodes : [] },
    renderTransaksi() { rendered = 'transaksi'; }, renderMaster() { rendered = 'master'; }, renderUsers() {} });
  const source = file('app.js');
  vm.runInContext(source.slice(source.indexOf('// ---------- tabs ----------'), source.indexOf('// mode Tagihan')), context);
  get('mobile-more-toggle').events.click();
  assert.equal(get('mobile-more').open, true);
  assert.equal(get('mobile-more-toggle').attrs['aria-expanded'], 'true');
  get('mobile-more').events.cancel({ preventDefault() {} });
  assert.equal(get('mobile-more').open, false);
  assert.equal(get('mobile-more-toggle').focused, true);
  assert.equal(get('mobile-more-toggle').attrs['aria-expanded'], 'false');
  get('mobile-more-toggle').events.click();
  nodes.find(n => n.dataset.view === 'master').events.click();
  assert.equal(rendered, 'master');
  assert.equal(get('mobile-more').open, false);
  assert.equal(nodes[6].attrs['aria-current'], 'page');
  nodes.find(n => n.dataset.view === 'transaksi').events.click();
  assert.equal(rendered, 'transaksi');
});

// Exercise the actual dashboard functions without authentication or a browser.
import vm from 'node:vm';
function dashboardHarness(report, transactions) {
  const elements = new Map();
  const get = id => {
    if (!elements.has(id)) elements.set(id, { value: '', textContent: '', innerHTML: '', style: {} });
    return elements.get(id);
  };
  const paths = [];
  const context = vm.createContext({
    $: get, URLSearchParams,
    rupiah: n => 'Rp' + (Number(n) || 0).toLocaleString('id-ID'),
    esc: s => String(s || '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])),
    renderCharts: async () => {},
    api: async path => {
      paths.push(path);
      if (path.startsWith('/api/laporan?')) return report;
      if (transactions instanceof Error) throw transactions;
      return transactions;
    },
  });
  const source = file('app.js');
  vm.runInContext(source.slice(source.indexOf('async function renderDashboard()'), source.indexOf('// ---------- grafik')), context);
  return { context, get, paths };
}

test('dashboard derives total funds from report and renders only five escaped period-filtered recent transactions', async () => {
  const rows = Array.from({ length: 7 }, (_, i) => ({ id: 7 - i, tanggal: '2026-11-02', jenis: i ? 'keluar' : 'masuk', unit: '<img src=x>', kategori: 'Obat', jumlah: 1000 + i, pasien: 'DO NOT DISPLAY PATIENT' }));
  const h = dashboardHarness({ kas_tunai: 250000, saldo_bank: 750000, masuk: 1000 }, rows);
  h.get('dash-dari').value = '2026-11-01';
  h.get('dash-sampai').value = '2026-11-02';
  await h.context.renderDashboard();
  assert.equal(h.get('card-dana').textContent, 'Rp1.000.000');
  assert.ok(h.paths.includes('/api/transaksi?dari=2026-11-01&sampai=2026-11-02'));
  const markup = h.get('dashboard-recent').innerHTML;
  assert.equal((markup.match(/class="recent-row/g) || []).length, 5);
  assert.ok(markup.includes('&lt;img src=x&gt;'));
  assert.ok(!markup.includes('<img'));
  assert.ok(!markup.includes('DO NOT DISPLAY PATIENT'));
  assert.ok(markup.includes('+Rp1.000'));
  assert.ok(markup.includes('−Rp1.001'));
});

test('recent transactions distinguish empty data from request failure', async () => {
  const empty = dashboardHarness({}, []);
  await empty.context.renderDashboard();
  assert.match(empty.get('dashboard-recent').innerHTML, /Belum ada transaksi pada periode ini/);
  const failure = dashboardHarness({}, new Error('offline'));
  await failure.context.renderDashboard();
  assert.match(failure.get('dashboard-recent').innerHTML, /Transaksi belum dapat dimuat/);
  assert.doesNotMatch(failure.get('dashboard-recent').innerHTML, /Belum ada transaksi pada periode ini/);
});


test('charts use distinct data colors while navigation exposes its current page', () => {
  const source = file('app.js');
  const nodes = [
    { dataset: { view: 'dashboard' }, attrs: {}, classList: { toggle() {} }, setAttribute(k, v) { this.attrs[k] = v; }, removeAttribute(k) { delete this.attrs[k]; } },
    { dataset: { view: 'master' }, attrs: {}, classList: { toggle() {} }, setAttribute(k, v) { this.attrs[k] = v; }, removeAttribute(k) { delete this.attrs[k]; } },
  ];
  const context = vm.createContext({
    document: { querySelectorAll: selector => selector === '[data-view]' ? nodes : [] },
    $: () => ({ classList: { add() {} } }), renderMaster() {}, renderUsers() {},
  });
  vm.runInContext(source.slice(source.indexOf('function switchView('), source.indexOf('// mode Tagihan')), context);
  context.switchView('master');
  assert.equal(nodes[1].attrs['aria-current'], 'page');
  assert.equal(nodes[0].attrs['aria-current'], undefined);
  const chart = vm.createContext({ esc: s => String(s) });
  vm.runInContext(source.slice(source.indexOf('function shortRp('), source.indexOf('// ---------- transaksi')), chart);
  const el = { innerHTML: '' };
  chart.drawArea(el, [{ tanggal: '2026-11-02', masuk: 1000, keluar: 400 }]);
  assert.ok(el.innerHTML.includes('stop-color="#168779"'));
  assert.ok(el.innerHTML.includes('stop-color="#e49532"'));
  const legend = { innerHTML: '' };
  chart.drawDonut(el, legend, Array.from({ length: 6 }, (_, i) => ({ nama: 'Unit ' + i, total: 100 })), 600);
  for (const color of ['#168779', '#4d83c6', '#e49532', '#8b6bb1', '#d03437', '#58a5b3']) {
    assert.ok(el.innerHTML.includes('stroke="' + color + '"'), color);
    assert.ok(legend.innerHTML.includes('background:' + color), 'matching legend ' + color);
  }
});


test('BPJS source is treated as a receivable: no method field, no manual claim form', () => {
  const html = file('index.html');
  assert.match(html, /id="t-bpjs-hint"/, 'form transaksi menjelaskan BPJS = piutang');
  assert.match(html, /id="t-metode-wrap"/, 'metode bayar bisa disembunyikan untuk BPJS');
  const klaimBlock = html.match(/<div id="tg-fields-klaim"[\s\S]*?<\/div>\s*<\/div>/)[0];
  assert.doesNotMatch(klaimBlock, /<input|<select/, 'klaim tidak punya input manual');

  const source = file('app.js');
  assert.match(source, /if \(!bpjs\) body\.metode_bayar_id/, 'metode tidak dikirim untuk BPJS');
  assert.match(source, /res\.pencatatan === 'piutang_bpjs'/, 'user diberi tahu hasilnya piutang');

  const els = {};
  const get = id => {
    if (!els[id]) els[id] = { value: '', disabled: false, classList: { toggle(cls, on) { this[cls] = on; } } };
    return els[id];
  };
  const context = vm.createContext({ $: get });
  vm.runInContext(
    source.slice(source.indexOf('function isBpjsSumber('), source.indexOf("$('t-sumber').addEventListener")),
    context,
  );
  context.MASTER = { sumber_bayar: [
    { id: 1, nama: 'Tunai / Umum', is_bpjs: false },
    { id: 2, nama: 'BPJS Kesehatan', is_bpjs: true },
  ] };
  get('t-jenis').value = 'masuk';

  get('t-sumber').value = '2';
  context.syncBpjsMode();
  assert.equal(get('t-metode-wrap').classList.hidden, true, 'metode disembunyikan untuk BPJS');
  assert.equal(get('t-metode').disabled, true, 'select tersembunyi ikut di-disable');
  assert.equal(get('t-bpjs-hint').classList.hidden, false, 'hint piutang tampil');

  get('t-sumber').value = '1';
  context.syncBpjsMode();
  assert.equal(get('t-metode-wrap').classList.hidden, false);
  assert.equal(get('t-metode').disabled, false);
  assert.equal(get('t-bpjs-hint').classList.hidden, true);
});
