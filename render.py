# Headless install: drives the picker page in headless Chrome so the frame goes through the exact same
# render → encode → install path as the "Set as wallpaper" button.
# usage: render.py <picker_url> <seconds>   (normally via ./picker <seconds>)
import asyncio, json, subprocess, sys, tempfile, time, urllib.request

import websockets

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9333


async def main(url, t):
    prof = tempfile.mkdtemp(prefix="ornn-picker-chrome-")
    proc = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={PORT}", f"--user-data-dir={prof}",
                             "--no-first-run", "--no-default-browser-check", "--use-angle=metal", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1)
                break
            except Exception:
                time.sleep(0.2)
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}/json/new?{url}", method="PUT")
        ws_url = json.load(urllib.request.urlopen(req))["webSocketDebuggerUrl"]
        async with websockets.connect(ws_url, max_size=None) as ws:
            seq = 0

            async def js(expr):
                nonlocal seq
                seq += 1
                await ws.send(json.dumps({"id": seq, "method": "Runtime.evaluate",
                                          "params": {"expression": expr, "awaitPromise": True, "returnByValue": True}}))
                while True:
                    msg = json.loads(await ws.recv())
                    if msg.get("id") == seq:
                        r = msg["result"]
                        if "exceptionDetails" in r:
                            raise RuntimeError(r["exceptionDetails"].get("exception", {}).get("description", r["exceptionDetails"]))
                        return r["result"].get("value")

            for _ in range(100):
                if await js("!!window.__picker"):
                    break
                await asyncio.sleep(0.2)
            await js("__picker.ready")
            t0 = time.time()
            out = await js(f"(async () => {{ __picker.setT({t}); return await __picker.exportFrame('install'); }})()")
            mb = {c: round(n / 1e6, 1) for c, n in out["sizes"].items()}
            trashed = out["result"]["trashed"]
            print(f"wallpaper set to {out['t']:.2f} s (copper {mb['copper']} MB, gray {mb['gray']} MB) in {time.time() - t0:.1f}s"
                  + (f"; trashed {', '.join(trashed)}" if trashed else ""))
            if not out["result"]["status"]["usesStable"]:
                print("note: your wallpaper isn't using ornn-fluted-copper.png / gray.png yet; choose one once in System Settings → Wallpaper")
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        subprocess.run(["rm", "-rf", prof])


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], float(sys.argv[2])))
