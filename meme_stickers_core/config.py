from typing import TYPE_CHECKING, cast

import skia
from pydantic import field_validator
from pydantic import BaseModel, Field

from .consts import (
    FLOAT_REGEX,
    FULL_HEX_COLOR_REGEX,
    SHORT_HEX_COLOR_REGEX,
    RGBAColorTuple,
    SkiaEncodedImageFormatType,
)

if TYPE_CHECKING:
    import re


def resolve_color_to_tuple(color: str) -> RGBAColorTuple:
    sm: re.Match[str] | None = None
    fm: re.Match[str] | None = None
    if (sm := SHORT_HEX_COLOR_REGEX.fullmatch(color)) or (
        fm := FULL_HEX_COLOR_REGEX.fullmatch(color)
    ):
        hex_str = (sm or cast("re.Match", fm))["hex"].upper()
        if sm:
            hex_str = "".join([x * 2 for x in hex_str])
        hex_str = f"{hex_str}FF" if len(hex_str) == 6 else hex_str
        return tuple(int(hex_str[i : i + 2], 16) for i in range(0, 8, 2))  # type: ignore

    if (
        (parts := color.lstrip("(").rstrip(")").split(","))
        and (3 <= len(parts) <= 4)
        # -
        and (parts := [part.strip() for part in parts])
        and all(x.isdigit() for x in parts[:3])
        # -
        and (rgb := [int(x) for x in parts[:3]])
        and all(0 <= int(x) <= 255 for x in rgb)
        # -
        and (
            (len(parts) == 3 and (a := 255))
            or (parts[3].isdigit() and 0 <= (a := int(parts[3])) <= 255)
            or (
                FLOAT_REGEX.fullmatch(parts[3])
                and 0 <= (a := int(float(parts[3]) * 255)) <= 255
            )
        )
    ):
        return (*rgb, a)  # type: ignore

    raise ValueError(
        f"Invalid color format: {color}."
        f" supported formats: #RGB, #RRGGBB"
        f", (R, G, B), (R, G, B, A), (R, G, B, a (0 ~ 1 float))",
    )


MIRROR_PRESETS: dict[str, dict[str, str]] = {
    "jsdelivr_mixed": {
        "github_url_template": "https://raw.githubusercontent.com/{owner}/{repo}/{ref_path}/{path}",
        "hub_manifest_url": "https://raw.githubusercontent.com/lgc-NB2Dev/meme-stickers-hub/main/manifest.json",
        "emoji_font_url": "https://cdn.jsdelivr.net/gh/googlefonts/noto-emoji@v2020-09-16-unicode13_1/fonts/NotoColorEmoji.ttf",
    },
    "official": {
        "github_url_template": "https://raw.githubusercontent.com/{owner}/{repo}/{ref_path}/{path}",
        "hub_manifest_url": "https://raw.githubusercontent.com/lgc-NB2Dev/meme-stickers-hub/main/manifest.json",
        "emoji_font_url": "https://raw.githubusercontent.com/googlefonts/noto-emoji/refs/tags/v2020-09-16-unicode13_1/fonts/NotoColorEmoji.ttf",
    },
    "ghfast": {
        "github_url_template": "https://ghfast.top/https://raw.githubusercontent.com/{owner}/{repo}/{ref_path}/{path}",
        "hub_manifest_url": "https://ghfast.top/https://raw.githubusercontent.com/lgc-NB2Dev/meme-stickers-hub/main/manifest.json",
        "emoji_font_url": "https://ghfast.top/https://raw.githubusercontent.com/googlefonts/noto-emoji/refs/tags/v2020-09-16-unicode13_1/fonts/NotoColorEmoji.ttf",
    },
    "ghproxy": {
        "github_url_template": "https://gh-proxy.com/https://raw.githubusercontent.com/{owner}/{repo}/{ref_path}/{path}",
        "hub_manifest_url": "https://gh-proxy.com/https://raw.githubusercontent.com/lgc-NB2Dev/meme-stickers-hub/main/manifest.json",
        "emoji_font_url": "https://gh-proxy.com/https://raw.githubusercontent.com/googlefonts/noto-emoji/refs/tags/v2020-09-16-unicode13_1/fonts/NotoColorEmoji.ttf",
    },
    "gitmirror": {
        "github_url_template": "https://raw.gitmirror.com/{owner}/{repo}/{ref_path}/{path}",
        "hub_manifest_url": "https://raw.gitmirror.com/lgc-NB2Dev/meme-stickers-hub/main/manifest.json",
        "emoji_font_url": "https://raw.gitmirror.com/googlefonts/noto-emoji/refs/tags/v2020-09-16-unicode13_1/fonts/NotoColorEmoji.ttf",
    },
    "kkgithub": {
        "github_url_template": "https://raw.kkgithub.com/{owner}/{repo}/{ref_path}/{path}",
        "hub_manifest_url": "https://raw.kkgithub.com/lgc-NB2Dev/meme-stickers-hub/main/manifest.json",
        "emoji_font_url": "https://raw.kkgithub.com/googlefonts/noto-emoji/refs/tags/v2020-09-16-unicode13_1/fonts/NotoColorEmoji.ttf",
    },
}


class ConfigModel(BaseModel):
    proxy: str | None = Field(None, alias="proxy")

    mirror_preset: str = "jsdelivr_mixed"

    github_url_template: str = (
        "https://raw.githubusercontent.com/{owner}/{repo}/{ref_path}/{path}"
    )
    hub_manifest_url: str = (
        "https://raw.githubusercontent.com/lgc-NB2Dev/meme-stickers-hub/main/manifest.json"
    )
    emoji_font_url: str = (
        "https://cdn.jsdelivr.net/gh/googlefonts/noto-emoji@v2020-09-16-unicode13_1/fonts/NotoColorEmoji.ttf"
    )
    retry_times: int = 3
    req_concurrency: int = 8
    req_timeout: int = 15

    auto_update: bool = True
    force_update: bool = False

    prompt_retries: int = 3
    prompt_timeout: int = 30

    default_sticker_background: int = 0xFFFFFFFF
    quote_reply: bool = True
    interactive_preview_image_format: SkiaEncodedImageFormatType = "jpeg"
    final_sticker_image_format: SkiaEncodedImageFormatType = "png"
    non_png_quality: int = 95

    @field_validator("default_sticker_background", mode="before")
    def _validate_str_color_to_int(cls, v):  # noqa: N805
        if isinstance(v, int):
            return v
        return skia.Color(*resolve_color_to_tuple(str(v)))


DEFAULT_CONFIG = ConfigModel()
config: ConfigModel = DEFAULT_CONFIG
data_dir = None


def update_config(config_dict: dict | None = None):
    global config
    base = DEFAULT_CONFIG.model_dump()
    if config_dict:
        preset_key = config_dict.get("mirror_preset")
        if preset_key and preset_key in MIRROR_PRESETS:
            preset_vals = MIRROR_PRESETS[preset_key]
            for k, v in preset_vals.items():
                if k not in config_dict or not config_dict[k]:
                    base[k] = v
        base.update(config_dict)
    new_cfg = ConfigModel(**base)
    for field in ConfigModel.model_fields:
        setattr(config, field, getattr(new_cfg, field))


def set_data_dir(path):
    global data_dir
    data_dir = path
