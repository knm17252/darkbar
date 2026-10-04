#!/usr/bin/env python3
"""PNG -> .icns, written next to this script.

    python3 make_icns.py icon.png            # makes icon.icns in this script's folder
    python3 make_icns.py icon.png --pad      # first shrink the art to 80% (the 824/1024 macOS icon margin)
    python3 make_icns.py                     # no argument: uses the only .png sitting next to this script

Tip: type "python3 make_icns.py " in Terminal, then drag the PNG into the window to paste its path.
Needs macOS (sips + iconutil). --pad also needs:  pip install pillow
"""
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIZES = [16, 32, 128, 256, 512]          # each also gets an @2x


def die(msg):
    sys.exit(f"error: {msg}")


def pick_source(args):
    if args:
        src = Path(args[0]).expanduser()
    else:
        pngs = sorted(HERE.glob("*.png"))
        if len(pngs) != 1:
            die("give me a PNG path, or leave exactly one .png next to this script")
        src = pngs[0]
    if not src.is_file() or src.suffix.lower() != ".png":
        die(f"not a PNG file: {src}")
    return src.resolve()


def padded(src, tmp):
    try:
        from PIL import Image
    except ImportError:
        die("--pad needs Pillow:  python3 -m pip install pillow")
    im = Image.open(src).convert("RGBA")
    side = max(im.size)
    inner = round(side * 824 / 1024)
    im = im.resize((inner, inner), Image.LANCZOS)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    off = (side - inner) // 2
    canvas.paste(im, (off, off), im)
    out = tmp / "padded.png"
    canvas.save(out)
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    pad = "--pad" in sys.argv[1:]
    src = pick_source(args)

    # sanity check on the source (sips prints "pixelWidth: N" etc.)
    info = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(src)],
                          capture_output=True, text=True).stdout.split()
    w, h = int(info[info.index("pixelWidth:") + 1]), int(info[info.index("pixelHeight:") + 1])
    if w != h:
        die(f"image must be square (got {w}x{h})")
    if w < 1024:
        print(f"warning: {w}px source; 1024px is needed for a sharp 512@2x")

    out = HERE / f"{src.stem}.icns"
    iconset = HERE / f"{src.stem}.iconset"
    shutil.rmtree(iconset, ignore_errors=True)
    iconset.mkdir()
    try:
        base = padded(src, iconset) if pad else src
        for s in SIZES:
            for scale, suffix in ((1, ""), (2, "@2x")):
                px = s * scale
                target = iconset / f"icon_{s}x{s}{suffix}.png"
                subprocess.run(["sips", "-z", str(px), str(px), str(base), "--out", str(target)],
                               check=True, capture_output=True)
        if pad:
            (iconset / "padded.png").unlink()        # keep only the real icon sizes in the iconset
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(out)], check=True)
    finally:
        shutil.rmtree(iconset, ignore_errors=True)
    print(f"made {out}")


if __name__ == "__main__":
    main()
