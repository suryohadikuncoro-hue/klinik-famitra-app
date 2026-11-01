"""Uji UI end-to-end lewat Chrome DevTools Protocol.

Login API -> set token di localStorage -> buka dashboard -> baca teks tiap tab.
Dipakai untuk membuktikan frontend benar-benar menarik data dari database
(Supabase/lokal) tanpa perlu melihat layar.
"""
import asyncio
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import websockets

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8200"
PORT = 9333
CHROME = r"C:/Program Files/Google/Chrome/Application/chrome.exe"
PROFILE = r"C:/Users/User/AppData/Local/hermes/cache/scratch/kfm/cdp-profile"


def login() -> str:
    req = urllib.request.Request(
        f"{BASE}/api/login",
        data=json.dumps({"username": "admin", "password": "admin123"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)["token"]


def ws_url() -> str:
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json", timeout=2) as r:
                for t in json.load(r):
                    if t["type"] == "page":
                        return t["webSocketDebuggerUrl"]
        except Exception:
            time.sleep(0.5)
    raise SystemExit("Chrome CDP tidak siap")


class CDP:
    def __init__(self, ws):
        self.ws = ws
        self.id = 0

    async def send(self, method, **params):
        self.id += 1
        await self.ws.send(json.dumps({"id": self.id, "method": method, "params": params}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("id") == self.id:
                return msg

    async def js(self, expr):
        r = await self.send(
            "Runtime.evaluate",
            expression=expr,
            returnByValue=True,
            awaitPromise=True,
        )
        return r.get("result", {}).get("result", {}).get("value")


async def main():
    token = login()
    print(f"token dari API: {len(token)} karakter")

    subprocess.Popen(
        [
            CHROME,
            "--headless=new",
            f"--remote-debugging-port={PORT}",
            f"--user-data-dir={PROFILE}",
            "--no-first-run",
            "--no-default-browser-check",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    async with websockets.connect(ws_url(), max_size=20_000_000) as ws:
        c = CDP(ws)
        await c.send("Page.enable")
        await c.send("Runtime.enable")
        await c.send("Page.navigate", url=BASE + "/")
        await asyncio.sleep(3)
        await c.js(f"localStorage.setItem('kfm_token', {json.dumps(token)})")
        await c.send("Page.navigate", url=BASE + "/")
        await asyncio.sleep(8)

        print("judul:", await c.js("document.title"))
        print("login-screen tampil:", await c.js(
            "getComputedStyle(document.querySelector('#login-screen')).display"
        ))
        print("\n--- DASHBOARD ---")
        print((await c.js("document.querySelector('#view-dashboard').innerText"))[:700])

        for view, label in [("transaksi", "TRANSAKSI"), ("kunjungan", "PENDAFTARAN"), ("pasien", "PASIEN")]:
            await c.js(f"document.querySelector('[data-view=\"{view}\"]').click()")
            await asyncio.sleep(4)
            txt = await c.js(f"document.querySelector('#view-{view}').innerText")
            print(f"\n--- {label} ---")
            print((txt or "")[:500])

        err = await c.js("window.__errors ? window.__errors.join(' | ') : 'tidak ada'")
        print("\nJS error:", err)


asyncio.run(main())
