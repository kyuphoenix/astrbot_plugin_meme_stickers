from __future__ import annotations

import io
import math
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageColor, ImageDraw, ImageFont

from ..consts import RGBAColorTuple, SkiaEncodedImageFormatType
from ..sticker_pack.models import StickerParams, StickerGridParams


def _rgba(c: RGBAColorTuple) -> tuple[int, int, int, int]:
    return int(c[0]), int(c[1]), int(c[2]), int(c[3])


def _fit_contain(w: float, h: float, tw: float, th: float) -> tuple[float, float, float, float]:
    r = min(tw / w, th / h)
    rw, rh = w * r, h * r
    return r, rw, rh, (tw - rw) / 2, (th - rh) / 2


@lru_cache(maxsize=512)
def _open_rgba(path: str) -> Image.Image:
    return Image.open(path).convert("RGBA")


@lru_cache(maxsize=1024)
def _resize_cached(path: str, w: int, h: int) -> Image.Image:
    return _open_rgba(path).resize((w, h), Image.Resampling.LANCZOS)


@lru_cache(maxsize=256)
def _font(path_or_name: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    p = Path(path_or_name)
    if p.exists():
        return ImageFont.truetype(str(p), size=size)
    try:
        return ImageFont.truetype(path_or_name, size=size)
    except Exception:
        return ImageFont.load_default()


def _pick_font(font_families: Iterable[str], size: float) -> ImageFont.ImageFont:
    s = max(1, int(round(size)))
    for name in font_families:
        try:
            return _font(name, s)
        except Exception:
            continue
    return ImageFont.load_default()


def render_sticker_image(
    base_path: Path,
    params: StickerParams,
    auto_resize: bool = False,
) -> Image.Image:
    canvas = Image.new("RGBA", (params.width, params.height), (0, 0, 0, 0))
    src_path = str(base_path / params.base_image)
    bg = _open_rgba(src_path)
    _, rw, rh, ox, oy = _fit_contain(bg.width, bg.height, params.width, params.height)
    bg = _resize_cached(src_path, int(round(rw)), int(round(rh)))
    canvas.alpha_composite(bg, (int(round(ox)), int(round(oy))))

    text = params.text or ""
    if not text:
        return canvas

    font_size = float(params.font_size)
    font = _pick_font(params.font_families, font_size)
    draw = ImageDraw.Draw(canvas)

    stroke_w = max(0, int(round(font_size * float(params.stroke_width_factor))))

    bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_w)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    if auto_resize and (tw > params.width or th > params.height):
        ratio = min(params.width / max(1, tw), params.height / max(1, th))
        font_size = max(1.0, font_size * ratio)
        font = _pick_font(params.font_families, font_size)
        stroke_w = max(0, int(round(font_size * float(params.stroke_width_factor))))
        bbox = draw.textbbox((0, 0), text, font=font, stroke_width=stroke_w)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    layer = Image.new("RGBA", (max(1, tw + 8), max(1, th + 8)), (0, 0, 0, 0))
    ldraw = ImageDraw.Draw(layer)
    ldraw.text(
        (4 - bbox[0], 4 - bbox[1]),
        text,
        font=font,
        fill=_rgba(params.text_color),
        stroke_fill=_rgba(params.stroke_color),
        stroke_width=stroke_w,
    )

    if abs(float(params.text_rotate_degrees)) > 1e-6:
        layer = layer.rotate(float(params.text_rotate_degrees), expand=True, resample=Image.Resampling.BICUBIC)

    tx = int(round(float(params.text_x) - layer.width / 2))
    ty = int(round(float(params.text_y) - layer.height / 2))
    tx = min(max(tx, 0), max(0, params.width - layer.width))
    ty = min(max(ty, 0), max(0, params.height - layer.height))

    canvas.alpha_composite(layer, (tx, ty))
    return canvas


def encode_image(img: Image.Image, image_format: SkiaEncodedImageFormatType, quality: int = 95, background: int | None = None) -> bytes:
    fmt = image_format.upper()
    out = io.BytesIO()
    if fmt == "JPEG":
        if background is None:
            bg_rgba = (255, 255, 255, 255)
        else:
            a = (background >> 24) & 0xFF
            r = (background >> 16) & 0xFF
            g = (background >> 8) & 0xFF
            b = background & 0xFF
            bg_rgba = (r, g, b, a)
        base = Image.new("RGBA", img.size, bg_rgba)
        base.alpha_composite(img)
        base.convert("RGB").save(out, format="JPEG", quality=quality)
    else:
        img.save(out, format=fmt, quality=quality)
    return out.getvalue()


def render_sticker_grid_bytes(base_path: Path, stickers: list[StickerParams], cols: int = 2, bg=(40, 44, 52, 255)) -> bytes:
    if not stickers:
        return encode_image(Image.new("RGBA", (16, 16), (0, 0, 0, 0)), "jpeg")
    max_w = max(s.width for s in stickers)
    max_h = max(s.height for s in stickers)
    gap = 16
    pad = 16
    cols = max(1, min(cols, len(stickers)))
    rows = math.ceil(len(stickers) / cols)
    out = Image.new("RGBA", (pad * 2 + cols * max_w + (cols - 1) * gap, pad * 2 + rows * max_h + (rows - 1) * gap), bg)
    tile_cache: dict[tuple[str, int, int, str], Image.Image] = {}
    for i, s in enumerate(stickers):
        r, c = divmod(i, cols)
        x = pad + c * (max_w + gap)
        y = pad + r * (max_h + gap)
        k = (s.base_image, s.width, s.height, s.text)
        tile = tile_cache.get(k)
        if tile is None:
            tile = render_sticker_image(base_path, s, auto_resize=True)
            tile_cache[k] = tile
        _, rw, rh, ox, oy = _fit_contain(tile.width, tile.height, max_w, max_h)
        tile = tile.resize((int(rw), int(rh)), Image.Resampling.LANCZOS)
        out.alpha_composite(tile, (int(x + ox), int(y + oy)))
    return encode_image(out, "jpeg")


def render_sticker_grid_with_params_bytes(base_path: Path, grid: StickerGridParams, stickers: list[StickerParams]) -> bytes:
    if not stickers:
        return encode_image(Image.new("RGBA", (16, 16), (0, 0, 0, 0)), "jpeg")

    pad_t, pad_r, pad_b, pad_l = map(int, grid.resolved_padding)
    gap_x, gap_y = map(int, grid.resolved_gap)

    max_w = max(s.width for s in stickers)
    max_h = max(s.height for s in stickers)
    if grid.sticker_size_fixed:
        max_w, max_h = int(grid.sticker_size_fixed[0]), int(grid.sticker_size_fixed[1])

    if grid.rows is not None:
        rows = min(int(grid.rows), len(stickers))
        cols = math.ceil(len(stickers) / max(1, rows))
    else:
        cols = max(1, min(int(grid.cols or 1), len(stickers)))
        rows = math.ceil(len(stickers) / cols)

    w = pad_l + pad_r + cols * max_w + (cols - 1) * gap_x
    h = pad_t + pad_b + rows * max_h + (rows - 1) * gap_y
    out = Image.new("RGBA", (w, h), (40, 44, 52, 255))

    # Grid background: support color tuple or image path.
    if isinstance(grid.background, str):
        bg_src = str(base_path / grid.background)
        bg = _open_rgba(bg_src)
        ratio = max(w / bg.width, h / bg.height)
        rw, rh = int(bg.width * ratio), int(bg.height * ratio)
        bg = _resize_cached(bg_src, rw, rh)
        ox = int((w - rw) / 2)
        oy = 0  # top-aligned cover
        out.alpha_composite(bg, (ox, oy))
    else:
        out = Image.new("RGBA", (w, h), _rgba(grid.background))

    tile_cache: dict[tuple[str, int, int, str], Image.Image] = {}
    for i, s in enumerate(stickers):
        r, c = divmod(i, cols)
        x = pad_l + c * (max_w + gap_x)
        y = pad_t + r * (max_h + gap_y)
        k = (s.base_image, s.width, s.height, s.text)
        tile = tile_cache.get(k)
        if tile is None:
            tile = render_sticker_image(base_path, s, auto_resize=True)
            tile_cache[k] = tile
        _, rw, rh, ox, oy = _fit_contain(tile.width, tile.height, max_w, max_h)
        tile = tile.resize((int(rw), int(rh)), Image.Resampling.LANCZOS)
        out.alpha_composite(tile, (int(x + ox), int(y + oy)))

    return encode_image(out, "jpeg")


def render_pack_list_bytes(items: list[dict]) -> bytes:
    cards: list[Image.Image] = []
    for it in items:
        s: StickerParams = it["sample_sticker_params"]
        preview = render_sticker_image(Path(it["base_path"]), s, auto_resize=True).resize((128, 128), Image.Resampling.LANCZOS)
        card = Image.new("RGBA", (740, 170), (64, 71, 84, 255))
        card.alpha_composite(preview, (16, 21))
        d = ImageDraw.Draw(card)
        title = f"{it.get('index','')}. {it.get('name','')} [{it.get('slug','')}]"
        desc = it.get("description", "")
        d.text((160, 28), title, fill=(215, 218, 224, 255))
        d.text((160, 78), desc, fill=(171, 178, 191, 255))
        cards.append(card)
    if not cards:
        return encode_image(Image.new("RGBA", (16, 16), (0, 0, 0, 0)), "jpeg")
    cols, gap, pad = 2, 16, 16
    rows = math.ceil(len(cards) / cols)
    cw, ch = cards[0].size
    out = Image.new("RGBA", (pad * 2 + cols * cw + (cols - 1) * gap, pad * 2 + rows * ch + (rows - 1) * gap), (40, 44, 52, 255))
    for i, c in enumerate(cards):
        r, cc = divmod(i, cols)
        out.alpha_composite(c, (pad + cc * (cw + gap), pad + r * (ch + gap)))
    return encode_image(out, "jpeg")
