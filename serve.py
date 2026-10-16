# Local helper for the picker: serves the page and installs rendered frames into ~/Pictures/Wallpapers.
# usage: python3 serve.py [--port 8765]   (normally started by ./picker)
#
# Wallpapers live at stable paths (ornn-fluted-copper.png / ornn-fluted-gray.png) because macOS stores the
# wallpaper as a file path. Installing replaces the file atomically, then restarts WallpaperAgent so the new
# image shows immediately; the restart re-reads the files and leaves the wallpaper settings untouched.
import argparse, json, os, plistlib, re, shutil, struct, subprocess, threading, time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WALLPAPERS = Path.home() / "Pictures" / "Wallpapers"
TRASH = Path.home() / ".Trash"
WALLPAPER_INDEX = Path.home() / "Library/Application Support/com.apple.wallpaper/Store/Index.plist"
COLOURS = ("copper", "gray")
SIZE = (5120, 2880)
LEGACY = re.compile(r"^ornn-fluted-(copper|gray)(-.+)?\.png$")  # older per-frame names
IDLE_EXIT_S = 3 * 3600

last_request = time.monotonic()


def stable_path(colour):
    return WALLPAPERS / f"ornn-fluted-{colour}.png"


def png_chunks(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG")
    i, out = 8, []
    while i + 8 <= len(data):
        n, = struct.unpack(">I", data[i:i + 4])
        kind = data[i + 4:i + 8].decode("latin1")
        if i + 12 + n > len(data):  # truncated read of a file head
            break
        out.append((kind, data[i + 8:i + 8 + n]))
        i += 12 + n
    return out


def frame_info(data):
    # The page writes {"t", "colour", ...} into a tEXt chunk keyed "ornn-frame"
    for kind, body in png_chunks(data):
        if kind == "tEXt" and body.startswith(b"ornn-frame\0"):
            return json.loads(body.split(b"\0", 1)[1])
    return None


def validate(data, colour):
    chunks = dict(png_chunks(data))
    w, h, depth, ctype = struct.unpack(">IIBB", chunks["IHDR"][:10])
    if (w, h) != SIZE or depth != 8 or ctype != 2:
        raise ValueError(f"expected 8-bit RGB {SIZE[0]}x{SIZE[1]}, got {w}x{h} depth {depth} type {ctype}")
    if not chunks.get("iCCP", b"").startswith(b"sRGB IEC61966-2.1\0"):
        raise ValueError("missing embedded sRGB profile")
    info = frame_info(data)
    if not info or info.get("colour") != colour:
        raise ValueError("missing or mismatched ornn-frame metadata")
    return info


def wallpaper_paths():
    # Every image path the wallpaper settings point at, including SystemDefault (read-only)
    try:
        index = plistlib.loads(WALLPAPER_INDEX.read_bytes())
    except Exception:
        return []
    found = []

    def walk(node):
        if isinstance(node, dict):
            blob = node.get("Configuration")
            if isinstance(blob, bytes):
                try:
                    url = plistlib.loads(blob).get("url", {}).get("relative", "")
                    if url.startswith("file://"):
                        found.append(url[len("file://"):])
                except Exception:
                    pass
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(index)
    return sorted(set(found))


def status():
    files = {}
    for c in COLOURS:
        p = stable_path(c)
        if p.exists():
            with p.open("rb") as f:
                head = f.read(65536)  # metadata chunks sit before the image data
            files[c] = {"path": str(p), "info": frame_info(head), "mtime": p.stat().st_mtime}
        else:
            files[c] = None
    in_use = wallpaper_paths()
    legacy = sorted(p.name for p in WALLPAPERS.glob("ornn-fluted-*.png") if LEGACY.match(p.name) and p.name not in {stable_path(c).name for c in COLOURS})
    return {
        "dir": str(WALLPAPERS),
        "files": files,
        "wallpaper": in_use,
        "usesStable": any(path in in_use for path in (str(stable_path(c)) for c in COLOURS)),
        "legacy": legacy,
    }


def install(colour, data):
    info = validate(data, colour)
    WALLPAPERS.mkdir(parents=True, exist_ok=True)
    tmp = stable_path(colour).with_suffix(".png.partial")
    tmp.write_bytes(data)
    os.replace(tmp, stable_path(colour))
    return info


def finish():
    # Trash older per-frame files, except any the wallpaper settings still point at
    in_use = set(wallpaper_paths())
    trashed, kept = [], []
    for name in status()["legacy"]:
        p = WALLPAPERS / name
        if str(p) in in_use:
            kept.append(name)
            continue
        dest = TRASH / name
        if dest.exists():
            dest = TRASH / f"{p.stem} {time.strftime('%H.%M.%S')}{p.suffix}"
        shutil.move(p, dest)
        trashed.append(name)
    subprocess.run(["killall", "WallpaperAgent"], capture_output=True)
    return {"trashed": trashed, "keptInUse": kept}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT), **kw)

    def log_message(self, format, *args):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _guard(self):
        # Writes only from our own page: same host, plus a custom header that cross-site pages cannot send
        host_ok = self.headers.get("Host", "").startswith(("127.0.0.1:", "localhost:"))
        if not host_ok or self.headers.get("X-Ornn-Picker") != "1":
            self._json(403, {"error": "forbidden"})
            return False
        return True

    def do_GET(self):
        global last_request
        last_request = time.monotonic()
        if self.path == "/api/status":
            return self._json(200, status())
        if self.path.startswith("/api/"):
            return self._json(404, {"error": "not found"})
        if self.path.split("?")[0] not in ("/", "/index.html"):
            return self._json(404, {"error": "not found"})
        return super().do_GET()

    def do_PUT(self):
        global last_request
        last_request = time.monotonic()
        if not self._guard():
            return
        m = re.fullmatch(r"/api/wallpaper/(copper|gray)", self.path)
        if not m:
            return self._json(404, {"error": "not found"})
        n = int(self.headers.get("Content-Length", 0))
        if n > 64 * 1024 * 1024:
            return self._json(413, {"error": "too large"})
        try:
            info = install(m.group(1), self.rfile.read(n))
        except Exception as e:
            return self._json(400, {"error": str(e)})
        self._json(200, {"ok": True, "info": info, "path": str(stable_path(m.group(1)))})

    def do_POST(self):
        global last_request
        last_request = time.monotonic()
        if not self._guard():
            return
        if self.path != "/api/finish":
            return self._json(404, {"error": "not found"})
        self._json(200, {"ok": True, **finish(), "status": status()})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)

    def reaper():
        while time.monotonic() - last_request < IDLE_EXIT_S:
            time.sleep(60)
        server.shutdown()

    threading.Thread(target=reaper, daemon=True).start()
    print(f"ornn picker on http://127.0.0.1:{args.port}/ (exits after {IDLE_EXIT_S // 3600} h idle)", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
