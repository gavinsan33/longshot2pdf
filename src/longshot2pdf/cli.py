"""Slice a very tall screenshot into pages and write a multipage PDF."""
import argparse
import io
import sys
from pathlib import Path

import img2pdf
import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None  # long screenshots easily exceed Pillow's default limit

PAGES = {"a4": (210.0, 297.0), "letter": (215.9, 279.4), "legal": (215.9, 355.6)}
MM_TO_PT = 72 / 25.4


def blank_rows(arr: np.ndarray, tol: int) -> np.ndarray:
    """True for rows that are a single flat color (safe places to cut)."""
    return (arr.max(axis=(1, 2)).astype(int) - arr.min(axis=(1, 2)).astype(int)) <= tol


def plan_cuts(img: Image.Image, page_h: int, smart: bool, window: float, tol: int):
    """Return (top, bottom) pixel bounds for each page."""
    h = img.height
    blank = blank_rows(np.asarray(img), tol) if smart else None
    cuts, top = [], 0
    while top < h:
        end = min(top + page_h, h)
        if end < h and smart:
            lo = max(top + int(page_h * (1 - window)), top + 1)
            idx = np.nonzero(blank[lo:end])[0]
            if idx.size:
                end = lo + int(idx[-1]) + 1  # cut after the last blank row in range
        cuts.append((top, end))
        top = end
    return cuts


def main(argv=None):
    p = argparse.ArgumentParser(prog="longshot2pdf", description=__doc__)
    p.add_argument("input", type=Path, help="long screenshot (png/jpg/webp/...)")
    p.add_argument("-o", "--output", type=Path, help="output PDF (default: input name + .pdf)")
    p.add_argument("-p", "--page", default="a4", choices=PAGES, help="page size (default a4)")
    p.add_argument("-m", "--margin", type=float, default=10, help="page margin in mm (default 10)")
    p.add_argument("--no-smart", action="store_true", help="cut at exact page height, ignoring content")
    p.add_argument("--window", type=float, default=0.15,
                   help="fraction of page height to search back for a clean cut (default 0.15)")
    p.add_argument("--tolerance", type=int, default=8,
                   help="max pixel-value spread for a row to count as blank (default 8)")
    a = p.parse_args(argv)

    out = a.output or a.input.with_suffix(".pdf")
    img = Image.open(a.input)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, "white")
        img = Image.alpha_composite(bg, img)
    img = img.convert("RGB")

    pw, ph = PAGES[a.page]
    cw, ch = pw - 2 * a.margin, ph - 2 * a.margin
    if cw <= 0 or ch <= 0:
        sys.exit("margin too large for page")
    page_h = max(1, int(img.width * ch / cw))  # pixels of source per page

    cuts = plan_cuts(img, page_h, not a.no_smart, a.window, a.tolerance)
    bgcolor = img.getpixel((0, 0))
    pages = []
    for top, bottom in cuts:
        # pad every slice to a uniform size so all pages scale identically
        tile = Image.new("RGB", (img.width, page_h), bgcolor)
        tile.paste(img.crop((0, top, img.width, bottom)), (0, 0))
        buf = io.BytesIO()
        tile.save(buf, "PNG")
        pages.append(buf.getvalue())

    layout = img2pdf.get_layout_fun(
        pagesize=(pw * MM_TO_PT, ph * MM_TO_PT),
        border=(a.margin * MM_TO_PT, a.margin * MM_TO_PT),
        fit=img2pdf.FitMode.into,
    )
    out.write_bytes(img2pdf.convert(pages, layout_fun=layout))
    print(f"{out}: {len(pages)} pages from {img.width}x{img.height}px")


if __name__ == "__main__":
    main()
