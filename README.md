# Ornn frame picker

Picks a frame of ornn.com's fluted-glass hero shader and sets it as the Mac wallpaper. It renders the site's own WebGL shader, so there's no video involved.

## Use

```sh
./picker          # open the picker in Chrome, scrub to a frame, click "Set as wallpaper"
./picker 385.5    # same result headlessly, for a frame time in seconds
```

"Set as wallpaper" renders copper and gray at 5120×2880 with 128 passes. It writes sRGB PNGs (8-bit RGB, embedded macOS sRGB profile, frame metadata in a `tEXt` chunk) and replaces these files in place:

- `~/Pictures/Wallpapers/ornn-fluted-copper.png`
- `~/Pictures/Wallpapers/ornn-fluted-gray.png`

It then restarts `WallpaperAgent`, so the desktop shows the new frame immediately.

**One-time setup:** in System Settings → Wallpaper, choose one of those two files with "Fill Screen". macOS stores the wallpaper as a path, and that path never changes after this.

## Why this setup

- **5120×2880 serves both displays.** It's native on the Dell S2725QC at "looks like 2560×1440". On the MacBook Air 13″ at "More Space" (3420×2224 backing), Fill Screen scales it to 0.772× and trims 267 px per side, which is the dashed area in the picker. Neither display ever upscales it.
- **The animation loops every 20π / (0.8 × 0.15) ≈ 523.6 s,** so the picker covers exactly one loop.
- **Reload by restarting the agent, not by API.** `killall WallpaperAgent` makes macOS re-read the replaced file and leaves wallpaper settings untouched. `NSWorkspace.setDesktopImageURL` also reloads it, but rewrites the "all displays" setting into a per-Space entry.
- **Safe cleanup.** Older per-frame files (`ornn-fluted-*-t…s-…png`) go to the Trash on save, except any file the wallpaper settings still point at.

## Files

- `index.html`: the built page. Don't edit it; run `python3 build.py`.
- `src/template.html`: the page source (UI, WebGL accumulation renderer, PNG encoder).
- `src/bands.frag`: ornn.com's shader, verbatim. `build.py` applies three marked patches.
- `src/srgb-iccp.b64`: the PNG `iCCP` payload, made from `/System/Library/ColorSync/Profiles/sRGB Profile.icc`.
- `serve.py`: localhost helper. It serves the page and handles `GET /api/status`, `PUT /api/wallpaper/{copper,gray}` and `POST /api/finish`. It exits after 3 h idle.
- `render.py`: headless Chrome driver used by `./picker <seconds>`.
