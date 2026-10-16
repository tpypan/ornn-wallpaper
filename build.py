# Builds index.html from src/: the vendored ornn.com shader, the page template and the sRGB ICC chunk.
# usage: python3 build.py
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"

# Picker patches to the verbatim shader: tiled rendering + subpixel/noise jitter + running sum for accumulation
PATCHES = [
    ("    vec2 fragCoord = v_uv * u_resolution;",
     "    vec2 fragCoord = v_uv * u_tile + u_offset + u_jitter.xy; // picker: tiles + subpixel jitter"),
    ("    seed = uvec3(uvec2(fragCoord), uint(fract(u_time) * 1000.0));",
     "    seed = uvec3(uvec2(fragCoord), uint(fract(u_time) * 1000.0) + uint(u_jitter.z)); // picker: per-pass noise"),
    ("    fragColor = vec4(col, 1.0);\n}",
     "    fragColor = vec4(col, 1.0) + texelFetch(u_prev, ivec2(gl_FragCoord.xy), 0); // picker: running sum\n}"),
]


def main():
    frag = (SRC / "bands.frag").read_text(encoding="utf8")
    assert "`" not in frag and "${" not in frag
    for old, new in PATCHES:
        assert frag.count(old) == 1, f"shader patch target not found: {old!r}"
        frag = frag.replace(old, new)
    html = (SRC / "template.html").read_text(encoding="utf8")
    html = html.replace("__FRAGMENT__", frag).replace("__ICCP_B64__", (SRC / "srgb-iccp.b64").read_text().strip())
    (ROOT / "index.html").write_text(html, encoding="utf8")
    print(f"built index.html ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
