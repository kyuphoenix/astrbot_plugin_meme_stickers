from asyncio import InvalidStateError
from contextlib import contextmanager, suppress
from textwrap import indent
from typing import Any, TypeAlias, TypeVar

from pydantic import BaseModel, ValidationError, field_validator, model_validator

from ..compat import deep_merge
from ..consts import (
    RGBAColorTuple,
    SkiaFontStyleType,
    SkiaTextAlignType,
    StickerGridGapType,
    StickerGridPaddingType,
    TRBLPaddingTuple,
    XYGapTuple,
)
from ..utils.file_source import FileSource

T = TypeVar("T")


def validate_not_falsy(v: T) -> T:
    if not v:
        raise ValueError("value cannot be empty")
    return v


@contextmanager
def wrap_validation_error(msg: str):
    try:
        yield
    except ValidationError as e:
        info = indent(str(e), "    ")
        raise ValueError(f"{msg}\n{info}") from e


class StickerParams(BaseModel):
    width: int
    height: int
    base_image: str
    text: str
    text_x: float
    text_y: float
    text_align: SkiaTextAlignType
    text_rotate_degrees: float
    text_color: RGBAColorTuple
    stroke_color: RGBAColorTuple
    stroke_width_factor: float
    font_size: float
    font_style: SkiaFontStyleType
    font_families: list[str]


class StickerParamsOptional(BaseModel):
    width: int | None = None
    height: int | None = None
    base_image: str | None = None
    text: str | None = None
    text_x: float | None = None
    text_y: float | None = None
    text_align: SkiaTextAlignType | None = None
    text_rotate_degrees: float | None = None
    text_color: RGBAColorTuple | None = None
    stroke_color: RGBAColorTuple | None = None
    stroke_width_factor: float | None = None
    font_size: float | None = None
    font_style: SkiaFontStyleType | None = None
    font_families: list[str] | None = None


class StickerInfoOptionalParams(BaseModel):
    name: str
    category: str
    params: StickerParamsOptional

    @field_validator("name", "category")
    @classmethod
    def _validate_not_falsy(cls, v: str) -> str:
        return validate_not_falsy(v)


class StickerInfo(BaseModel):
    name: str
    category: str
    params: StickerParams


class StickerExternalFont(BaseModel):
    path: str


class StickerPackConfig(BaseModel):
    update_source: FileSource | None = None
    disabled: bool = False
    commands: list[str] = []
    extend_commands: list[str] = []


class StickerGridParams(BaseModel):
    padding: StickerGridPaddingType = 16
    gap: StickerGridGapType = 16
    rows: int | None = None
    cols: int | None = 5
    background: RGBAColorTuple | str = (40, 44, 52, 255)
    sticker_size_fixed: tuple[int, int] | None = None

    @model_validator(mode="after")
    def _validate_rows_cols(self):
        if (self.rows is None and self.cols is None) or (self.rows is not None and self.cols is not None):
            raise ValueError("Either rows or cols must be None")
        return self

    @property
    def resolved_padding(self) -> TRBLPaddingTuple:
        if isinstance(self.padding, (int, float)):
            p = self.padding
            return (p, p, p, p)
        if len(self.padding) == 1:
            p = self.padding[0]
            return (p, p, p, p)
        if len(self.padding) == 2:
            x, y = self.padding
            return (x, y, x, y)
        return self.padding

    @property
    def resolved_gap(self) -> XYGapTuple:
        if isinstance(self.gap, (int, float)):
            g = self.gap
            return (g, g)
        if len(self.gap) == 1:
            g = self.gap[0]
            return (g, g)
        return self.gap


class StickerGridSetting(BaseModel):
    disable_category_select: bool = False
    default_params: StickerGridParams = StickerGridParams()
    category_override_params: StickerGridParams = StickerGridParams()
    stickers_override_params: dict[str, StickerGridParams] = {}

    resolved_category_params: StickerGridParams = StickerGridParams()
    resolved_stickers_params: dict[str, StickerGridParams] = {}

    @model_validator(mode="after")
    def _validate_resolve_overrides(self):
        with wrap_validation_error("category_select_override_params validation failed"):
            self.resolved_category_params = StickerGridParams.model_validate(
                deep_merge(
                    self.default_params.model_dump(exclude_unset=True),
                    self.category_override_params.model_dump(exclude_unset=True),
                ),
            )
        resolved: dict[str, StickerGridParams] = {}
        for category, params in self.stickers_override_params.items():
            with wrap_validation_error(f"category {category} overridden StickerGridSetting validation failed"):
                resolved[category] = StickerGridParams.model_validate(
                    deep_merge(
                        self.default_params.model_dump(exclude_unset=True),
                        params.model_dump(exclude_unset=True),
                    ),
                )
        self.resolved_stickers_params = resolved
        return self


def merge_ensure_sticker_params(*params: StickerParamsOptional) -> StickerParams:
    kw: dict[str, Any] = {}
    for param in params:
        kw.update(param.model_dump(exclude_defaults=True))
    return StickerParams(**kw)


def find_sticker_by_name(stickers: list[StickerInfo], name: str) -> StickerInfo | None:
    return next((x for x in stickers if x.name == name), None)


def find_sticker(stickers: list[StickerInfo], query: str | int) -> StickerInfo | None:
    if isinstance(query, str) and (not query.isdigit()):
        return find_sticker_by_name(stickers, query)
    with suppress(IndexError):
        return stickers[int(query)]
    return None


class StickerPackManifest(BaseModel):
    version: int
    name: str
    description: str
    default_config: StickerPackConfig = StickerPackConfig()
    default_sticker_params: StickerParamsOptional = StickerParamsOptional()
    sticker_grid: StickerGridSetting = StickerGridSetting()
    sample_sticker: StickerInfoOptionalParams | str | int | None = None
    external_fonts: list[StickerExternalFont] = []
    stickers: list[StickerInfoOptionalParams]

    resolved_stickers: list[StickerInfo] = []
    resolved_sample_sticker_placeholder: StickerParams | None = None

    @property
    def resolved_sample_sticker(self) -> StickerParams:
        if self.resolved_sample_sticker_placeholder is None:
            raise InvalidStateError
        return self.resolved_sample_sticker_placeholder

    @property
    def resolved_stickers_by_category(self) -> dict[str, list[StickerInfo]]:
        categories = list({x.category for x in self.resolved_stickers})
        return {c: [x for x in self.resolved_stickers if x.category == c] for c in categories}

    def resolve_sticker_params(self, *args: StickerParamsOptional) -> StickerParams:
        return merge_ensure_sticker_params(self.default_sticker_params, *args)

    def find_sticker_by_name(self, name: str) -> StickerInfo | None:
        return find_sticker_by_name(self.resolved_stickers, name)

    def find_sticker(self, query: str | int) -> StickerInfo | None:
        return find_sticker(self.resolved_stickers, query)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return validate_not_falsy(v)

    @model_validator(mode="after")
    def _validate_resolve_stickers(self):
        if not self.stickers:
            raise ValueError("Stickers cannot be empty")

        def validate_info(sticker: StickerInfoOptionalParams) -> StickerInfo:
            return StickerInfo.model_validate(
                {
                    **sticker.model_dump(exclude={"params"}),
                    "params": merge_ensure_sticker_params(self.default_sticker_params, sticker.params),
                },
            )

        self.resolved_stickers = [validate_info(x) for x in self.stickers]

        sample_sticker = self.sample_sticker
        if not sample_sticker:
            resolved_sample_sticker = self.resolved_stickers[0].params
        elif isinstance(sample_sticker, StickerInfoOptionalParams):
            resolved_sample_sticker = merge_ensure_sticker_params(self.default_sticker_params, sample_sticker.params)
        else:
            it = find_sticker(self.resolved_stickers, sample_sticker)
            if it is None:
                raise ValueError(f"Sample sticker `{sample_sticker}` not found")
            resolved_sample_sticker = it.params
        self.resolved_sample_sticker_placeholder = resolved_sample_sticker
        return self


ChecksumDict: TypeAlias = dict[str, str]
OptionalChecksumDict: TypeAlias = dict[str, str | None]


class HubStickerPackInfo(BaseModel):
    slug: str
    source: FileSource


HubManifest: TypeAlias = list[HubStickerPackInfo]


def zoom_sticker(params: StickerParams, zoom: float, width: int | None = None, height: int | None = None) -> StickerParams:
    params.width = width or round(params.width * zoom)
    params.height = height or round(params.height * zoom)
    params.text_x *= zoom
    params.text_y *= zoom
    params.font_size *= zoom
    return params
