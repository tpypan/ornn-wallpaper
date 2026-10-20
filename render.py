# Headless install: drives the picker page in headless Chrome so the frame goes through the exact same
# render → encode → install path as the "Set as wallpaper" button. Standard library only.
# usage: render.py <picker_url> <seconds>   (normally via ./picker <seconds>)
import base64, json, os, shutil, socket, struct, subprocess, sys, tempfile, time, urllib.parse
from urllib.request import urlopen
from pathlib import Path

# Any Chromium browser works; $CHROME overrides the search
BROWSERS = ["Google Chrome", "Google Chrome Beta", "Google Chrome Canary", "Chromium", "Microsoft Edge", "Brave Browser"]


def find_browser():
    if os.environ.get("CHROME"):
        return os.environ["CHROME"]
    for root in (Path("/Applications"), Path.home() / "Applications"):
        for name in BROWSERS:
            exe = root / f"{name}.app/Contents/MacOS/{name}"
            if exe.exists():
                return str(exe)
    sys.exit("No Chromium browser found (looked for " + ", ".join(BROWSERS) + "). Set CHROME=/path/to/binary.")


class WebSocket:
    # Minimal RFC 6455 client: enough for the DevTools protocol on localhost (text frames, no extensions)
    def __init__(self, url):
        u = urllib.parse.urlparse(url)
        self.sock = socket.create_connection((u.hostname, u.port), timeout=600)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET {u.path} HTTP/1.1\r\nHost: {u.netloc}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                           f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("websocket handshake failed")
            head += chunk
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise ConnectionError(head.split(b"\r\n", 1)[0].decode(errors="replace"))
        self.buf = head.split(b"\r\n\r\n", 1)[1]

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(1 << 16)
            if not chunk:
                raise ConnectionError("websocket closed")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def send(self, text):
        data, mask = text.encode(), os.urandom(4)
        n = len(data)
        head = bytes([0x81]) + (bytes([0x80 | n]) if n < 126 else
                                struct.pack(">BH", 0x80 | 126, n) if n < 1 << 16 else struct.pack(">BQ", 0x80 | 127, n))
        self.sock.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def recv(self):
        message = b""
        while True:
            b0, b1 = self._read(2)
            n = b1 & 0x7F
            if n == 126:
                n, = struct.unpack(">H", self._read(2))
            elif n == 127:
                n, = struct.unpack(">Q", self._read(8))
            payload = self._read(n)
            op = b0 & 0x0F
            if op == 0x8:
                raise ConnectionError("websocket closed by browser")
            if op in (0x0, 0x1, 0x2):
                message += payload
                if b0 & 0x80:
                    return message.decode()

    def close(self):
        self.sock.close()


def main(url, t):
    prof = tempfile.mkdtemp(prefix="ornn-picker-chrome-")
    # Port 0 lets Chrome pick a free port and write it to DevToolsActivePort
    proc = subprocess.Popen([find_browser(), "--headless=new", "--remote-debugging-port=0", f"--user-data-dir={prof}",
                             "--no-first-run", "--no-default-browser-check", "--use-angle=metal", url],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ws = None
    try:
        port_file = Path(prof) / "DevToolsActivePort"
        for _ in range(150):
            if port_file.exists() and port_file.read_text().strip():
                break
            time.sleep(0.2)
        else:
            sys.exit("headless browser didn't start")
        port = port_file.read_text().split()[0]
        for _ in range(50):
            pages = [p for p in json.load(urlopen(f"http://127.0.0.1:{port}/json/list")) if p.get("type") == "page"]
            if pages:
                break
            time.sleep(0.2)
        else:
            sys.exit("headless browser didn't open the picker page")
        ws = WebSocket(pages[0]["webSocketDebuggerUrl"])
        seq = 0

        def js(expr):
            nonlocal seq
            seq += 1
            ws.send(json.dumps({"id": seq, "method": "Runtime.evaluate",
                                "params": {"expression": expr, "awaitPromise": True, "returnByValue": True}}))
            while True:
                msg = json.loads(ws.recv())
                if msg.get("id") == seq:
                    r = msg["result"]
                    if "exceptionDetails" in r:
                        raise RuntimeError(r["exceptionDetails"].get("exception", {}).get("description", r["exceptionDetails"]))
                    return r["result"].get("value")

        for _ in range(100):
            if js("!!window.__picker"):
                break
            time.sleep(0.2)
        js("__picker.ready")
        t0 = time.time()
        out = js(f"(async () => {{ __picker.setT({t}); return await __picker.exportFrame('install'); }})()")
        mb = {c: round(n / 1e6, 1) for c, n in out["sizes"].items()}
        print(f"wallpaper set to {out['t']:.2f} s at {out['w']}×{out['h']} "
              f"(copper {mb['copper']} MB, gray {mb['gray']} MB) in {time.time() - t0:.1f}s")
        if out["result"]["status"]["usesStable"] is False:
            print("note: your wallpaper isn't using ornn-fluted-copper.png / gray.png yet; choose one once in System Settings → Wallpaper")
    finally:
        if ws:
            ws.close()
        proc.terminate()
        proc.wait(timeout=10)
        shutil.rmtree(prof, ignore_errors=True)


if __name__ == "__main__":
    main(sys.argv[1], float(sys.argv[2]))
