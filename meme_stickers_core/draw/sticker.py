import math
from pathlib import Path

import skia

from ..sticker_pack.models import StickerParams
from .tools import (
    FONT_STYLE_FUNC_MAP,
    TEXT_ALIGN_MAP,
    calc_rotated_bounding_box_xywh,
    get_resize_contain_ratio_size_offset,
    make_stroke_paint,
    read_file_to_skia_image,
)


def _is_emoji(ch: str) -> bool:
    c = ord(ch)
    return (
        0x1F600 <= c <= 0x1F64F
        or 0x1F300 <= c <= 0x1F5FF
        or 0x1F680 <= c <= 0x1F6FF
        or 0x1F900 <= c <= 0x1F9FF
        or 0x2600 <= c <= 0x27BF
        or 0x1F1E6 <= c <= 0x1F1FF
    )


def _is_emoji_control(ch: str) -> bool:
    # Variation selectors / joiner controls should not be rendered alone.
    c = ord(ch)
    return c in {0xFE0E, 0xFE0F, 0x200D}


def _pick_typeface_from_paths(font_families: list[str]) -> skia.Typeface:
    for x in font_families:
        p = Path(x)
        if p.exists():
            tf = skia.Typeface.MakeFromFile(str(p))
            if tf:
                return tf
    raise RuntimeError("No valid font file found in font_families")


def _pick_emoji_typeface(custom_tf: skia.Typeface, font_families: list[str]) -> skia.Typeface:
    for x in font_families:
        p = Path(x)
        if p.name.lower() == "notocoloremoji.ttf" and p.exists():
            tf = skia.Typeface.MakeFromFile(str(p))
            if tf:
                return tf
    return custom_tf


def _font_style_to_skfontstyle(style: skia.FontStyle) -> skia.FontStyle:
    return style


def _build_line_tokens(text: str):
    tokens: list[tuple[str, bool]] = []
    for ch in text:
        if _is_emoji_control(ch):
            continue
        tokens.append((ch, _is_emoji(ch)))
    return tokens


def _measure_and_layout(
    text: str,
    text_x: float,
    text_y: float,
    font_size: float,
    font_families: list[str],
    font_style: skia.FontStyle,
    stroke_width_factor: float,
):
    custom_tf = _pick_typeface_from_paths(font_families)
    custom_font = skia.Font(custom_tf, font_size)
    custom_font.setEdging(skia.Font.Edging.kAntiAlias)

    emoji_tf = _pick_emoji_typeface(custom_tf, font_families)
    emoji_font = skia.Font(emoji_tf, font_size)
    emoji_font.setEdging(skia.Font.Edging.kAntiAlias)

    paint = skia.Paint(AntiAlias=True)
    metrics = custom_font.getMetrics()
    line_height = metrics.fDescent - metrics.fAscent + metrics.fLeading

    tokens = _build_line_tokens(text)
    chunks = []
    total_w = 0.0
    for ch, is_emo in tokens:
        f = emoji_font if is_emo else custom_font
        w = f.measureText(ch, skia.TextEncoding.kUTF8, None, paint)
        chunks.append((ch, is_emo, w))
        total_w += w

    stroke_w = font_size * stroke_width_factor
    box_w = total_w + stroke_w * 2
    box_h = line_height + stroke_w * 2

    # center alignment baseline behavior (legacy-consistent)
    offset_x = total_w / 2
    offset_y = -metrics.fAscent

    return {
        "custom_font": custom_font,
        "emoji_font": emoji_font,
        "chunks": chunks,
        "metrics": metrics,
        "line_height": line_height,
        "box": (text_x - offset_x - stroke_w, text_y - offset_y - stroke_w, box_w, box_h),
        "stroke_w": stroke_w,
        "total_w": total_w,
        "offset_x": offset_x,
        "offset_y": offset_y,
    }


def make_sticker_picture(
    width: int,
    height: int,
    base_image: skia.Image,
    text: str,
    text_x: float,
    text_y: float,
    text_align: skia.textlayout_TextAlign,
    text_rotate_degrees: float,
    text_color: int,
    stroke_color: int,
    stroke_width_factor: float,
    font_size: float,
    font_style: skia.FontStyle,
    font_families: list[str],
    auto_resize: bool = False,
    debug: bool = False,
) -> skia.Picture:
    pic_recorder = skia.PictureRecorder()
    canvas = pic_recorder.beginRecording(width, height)

    image_w = base_image.width()
    image_h = base_image.height()
    _, resized_width, resized_height, top_left_offset_x, top_left_offset_y = get_resize_contain_ratio_size_offset(
        image_w,
        image_h,
        width,
        height,
    )

    with skia.AutoCanvasRestore(canvas):
        image_rect = skia.Rect.MakeXYWH(top_left_offset_x, top_left_offset_y, resized_width, resized_height)
        if debug:
            canvas.drawRect(image_rect, make_stroke_paint(0xFF0000FF, 2))
        canvas.drawImageRect(base_image, image_rect, skia.SamplingOptions(skia.FilterMode.kLinear))

    if not text:
        return pic_recorder.finishRecordingAsPicture()

    def build_layout(size: float):
        return _measure_and_layout(
            text=text,
            text_x=text_x,
            text_y=text_y,
            font_size=size,
            font_families=font_families,
            font_style=font_style,
            stroke_width_factor=stroke_width_factor,
        )

    layout = build_layout(font_size)

    def calc_text_rotated_xywh(lt):
        return calc_rotated_bounding_box_xywh(lt["box"], (text_x, text_y), text_rotate_degrees)

    if auto_resize:
        bx, by, bw, bh = calc_text_rotated_xywh(layout)
        if bw > width or bh > height:
            ratio = min(width / bw, height / bh)
            font_size = max(1.0, font_size * ratio)
            layout = build_layout(font_size)
            bx, by, bw, bh = calc_text_rotated_xywh(layout)

        if bx < 0:
            text_x_adj = -bx
        else:
            text_x_adj = 0
        if by < 0:
            text_y_adj = -by
        else:
            text_y_adj = 0
        if bx + bw > width:
            text_x_adj -= (bx + bw - width)
        if by + bh > height:
            text_y_adj -= (by + bh - height)

        if text_x_adj or text_y_adj:
            text_x += text_x_adj
            text_y += text_y_adj
            layout = build_layout(font_size)

    if debug:
        with skia.AutoCanvasRestore(canvas):
            canvas.drawRect(skia.Rect.MakeXYWH(*calc_text_rotated_xywh(layout)), make_stroke_paint(0xFFFF0000, 2))

    with skia.AutoCanvasRestore(canvas):
        canvas.translate(text_x, text_y)
        canvas.rotate(text_rotate_degrees)

        x = -layout["offset_x"]
        baseline_y = 0.0

        fill_paint = skia.Paint(AntiAlias=True, Color=text_color)
        stroke_paint = skia.Paint(AntiAlias=True, Color=stroke_color)
        stroke_paint.setStyle(skia.Paint.kStroke_Style)
        stroke_paint.setStrokeJoin(skia.Paint.kRound_Join)
        stroke_paint.setStrokeWidth(layout["stroke_w"])

        for ch, is_emo, w in layout["chunks"]:
            f = layout["emoji_font"] if is_emo else layout["custom_font"]
            if layout["stroke_w"] > 0:
                canvas.drawSimpleText(ch, x, baseline_y, f, stroke_paint)
            canvas.drawSimpleText(ch, x, baseline_y, f, fill_paint)
            x += w

    return pic_recorder.finishRecordingAsPicture()


def make_sticker_picture_from_params(
    base_path: Path,
    params: StickerParams,
    auto_resize: bool = False,
    debug: bool = False,
) -> skia.Picture:
    return make_sticker_picture(
        width=params.width,
        height=params.height,
        base_image=read_file_to_skia_image(base_path / params.base_image),
        text=params.text,
        text_x=params.text_x,
        text_y=params.text_y,
        text_align=TEXT_ALIGN_MAP[params.text_align],
        text_rotate_degrees=params.text_rotate_degrees,
        text_color=skia.Color(*params.text_color),
        stroke_color=skia.Color(*params.stroke_color),
        stroke_width_factor=params.stroke_width_factor,
        font_size=params.font_size,
        font_style=FONT_STYLE_FUNC_MAP[params.font_style](),
        font_families=params.font_families,
        auto_resize=auto_resize,
        debug=debug,
    )
