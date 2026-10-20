# Ornn wallpaper

Picks a frame of ornn.com's fluted-glass hero shader and sets it as the Mac wallpaper. It renders the site's own WebGL shader, so there's no video involved.

## Requirements

- macOS, Apple silicon or Intel. Reloading the wallpaper in place works best on macOS 14 Sonoma or later.
- Python 3.9+. Apple's command line tools include it (`xcode-select --install`). No packages are needed.
- Google Chrome is recommended. Any Chromium browser (Chrome, Chromium, Edge, Brave) works for `./picker <seconds>`. The picker UI also runs in Safari 16.4+.

## Use

```sh
./picker          # open the picker in the browser, scrub to a frame, click "Set as wallpaper"
./picker 385.5    # same result headlessly, for a frame time in seconds
```

"Set as wallpaper" renders copper and gray versions with 128 passes. It writes sRGB PNGs (8-bit RGB, embedded sRGB profile, frame metadata in a `tEXt` chunk) and replaces these files in place:

- `~/Pictures/Wallpapers/ornn-fluted-copper.png`
- `~/Pictures/Wallpapers/ornn-fluted-gray.png`

It then restarts `WallpaperAgent` (or the Dock on macOS 13 and earlier), so the desktop shows the new frame immediately.

**One-time setup:** in System Settings → Wallpaper, choose one of those two files with "Fill Screen". macOS stores the wallpaper as a path, and that path never changes after this.

## Image size

The size is read from the displays connected when the picker starts. The file is as wide as the widest display and as tall as the tallest, counted in backing pixels: the "looks like" resolution × 2 on Retina. "Fill Screen" therefore only ever shrinks the image on each display and trims whatever doesn't match that display's shape. Some examples:

| Setup | File size |
| --- | --- |
| 27″ 5K / Studio Display, or a 4K display at "looks like 2560×1440" | 5120×2880 |
| MacBook Air 13″ at default scaling | 2940×1912 |
| MacBook Pro 14″ at default scaling | 3024×1964 |
| Pro Display XDR | 6016×3384 |
| 5K display + MacBook Air | 5120×2880, and the Air trims the sides |

The picker draws a dashed box for each display that trims the image. "Preview framing" shows exactly what each display keeps.

Connect your largest display before saving. If you save while only a laptop screen is connected, the file is sized for the laptop, and a bigger display plugged in later will upscale it. The picker warns you before you replace a larger file with a smaller one.

## Options

Set these as environment variables, e.g. `ORNN_PICKER_SIZE=6016x3384 ./picker`:

- `ORNN_PICKER_SIZE=WxH`: fixes the export size instead of reading it from the displays.
- `ORNN_PICKER_PORT`: helper port (default 8765).
- `CHROME=/path/to/binary`: browser used by `./picker <seconds>`.

The helper keeps running in the background until it has been idle for 3 hours. It reads `ORNN_PICKER_SIZE` and `ORNN_PICKER_PORT` only when it starts. To change them, stop it first with `pkill -f 'serve.py --port'`.

## Notes

- **The animation loops every 20π / (0.8 × 0.15) ≈ 523.6 s,** so the picker covers exactly one loop.
- **The wallpaper reloads by restarting the agent, not through an API.** `killall WallpaperAgent` makes macOS re-read the replaced file and leaves the wallpaper settings untouched. `NSWorkspace.setDesktopImageURL` also reloads it, but rewrites the "all displays" setting into a per-Space entry.
- **The shader scales with image height,** so every size shows the same band width. Wider images just show more of the frame.

## Files

- `index.html`: the built page. Don't edit it; run `python3 build.py`.
- `src/template.html`: the page source (UI, WebGL accumulation renderer, PNG encoder).
- `src/bands.frag`: ornn.com's shader, verbatim. `build.py` applies three marked patches.
- `src/srgb-iccp.b64`: the PNG `iCCP` payload, made from `/System/Library/ColorSync/Profiles/sRGB Profile.icc`.
- `serve.py`: localhost helper. It serves the page and handles `GET /api/status` (files, displays, export size), `PUT /api/wallpaper/{copper,gray}` and `POST /api/finish`.
- `render.py`: headless Chrome driver used by `./picker <seconds>`. It uses only the standard library and includes a minimal DevTools WebSocket client.
