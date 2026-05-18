import asyncio
import hashlib
import json
import shutil
from collections.abc import Callable
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from typing_extensions import Unpack

from astrbot.api import logger

from ..consts import CONFIG_FILENAME, MANIFEST_FILENAME, UPDATING_FLAG_FILENAME
from ..utils.file_source import FileSource, ReqKwargs, fetch_source, with_kw_cli, with_kw_sem
from .hub import fetch_manifest, fetch_optional_checksum
from .models import StickerPackConfig, StickerPackManifest


def collect_manifest_files(manifest: StickerPackManifest) -> list[str]:
    files: list[str] = []
    if manifest.external_fonts:
        files.extend(x.path for x in manifest.external_fonts)
    if manifest.default_sticker_params.base_image:
        files.append(manifest.default_sticker_params.base_image)
    grid = manifest.sticker_grid
    files.extend(
        x
        for x in (
            grid.default_params.background,
            grid.category_override_params.background,
            *(x.background for x in grid.stickers_override_params.values()),
        )
        if isinstance(x, str)
    )
    files.extend(img for x in manifest.stickers if (img := x.params.base_image))
    return files


def collect_local_files(path: Path) -> list[str]:
    ignored_paths = {(path / x) for x in {MANIFEST_FILENAME, CONFIG_FILENAME}}
    return [
        x.relative_to(path).as_posix()
        for x in path.rglob("*")
        if x.is_file() and x not in ignored_paths
    ]


@dataclass
class UpdatedResourcesInfo:
    assets: set[str]
    fonts: set[str]


async def update_sticker_pack(
    pack_path: Path,
    source: FileSource,
    manifest: StickerPackManifest | None = None,
    file_update_start_callback: Callable[[], Any] | None = None,
    **req_kw: Unpack[ReqKwargs],
):
    slug = pack_path.name
    if (pack_path / UPDATING_FLAG_FILENAME).exists():
        raise RuntimeError(f"Pack `{slug}` is updating")

    if manifest is None:
        manifest = await fetch_manifest(source, **req_kw)
    checksum = await fetch_optional_checksum(source, **req_kw)

    local_files = set(collect_local_files(pack_path)) if pack_path.exists() else set[str]()
    remote_files = set(collect_manifest_files(manifest))

    files_should_download = remote_files - local_files
    exist_files_not_in_pack_dir = {x for x in files_should_download if (pack_path / x).exists()}
    files_should_download -= exist_files_not_in_pack_dir

    file_both_exist = ({*local_files, *exist_files_not_in_pack_dir} & remote_files)
    if checksum:
        both_exist_checksum = {x: hashlib.sha256((pack_path / x).read_bytes()).hexdigest() for x in file_both_exist}
        files_should_download.update(x for x, c in both_exist_checksum.items() if checksum.get(x) != c)
    else:
        files_should_download.update(file_both_exist)

    async def download(base: Path, path: str):
        r = await fetch_source(source, path, **req_kw)
        p = base / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(r.content)

    @contextmanager
    def file_updating_ctx():
        pack_path.mkdir(parents=True, exist_ok=True)
        flag_path = pack_path / UPDATING_FLAG_FILENAME
        flag_path.touch()
        if file_update_start_callback:
            file_update_start_callback()
        try:
            yield
        finally:
            flag_path.unlink(missing_ok=True)

    def after_ops():
        for path in (local_files - remote_files):
            (pack_path / path).unlink(missing_ok=True)

        for p in tuple(p for p in pack_path.rglob("*") if p.is_dir() and not any(p.iterdir())):
            p.rmdir()

        (pack_path / MANIFEST_FILENAME).write_text(
            json.dumps(manifest.model_dump(exclude_defaults=True, exclude_unset=True), ensure_ascii=False, indent=2),
            "u8",
        )

        config_path = pack_path / CONFIG_FILENAME
        config = StickerPackConfig.model_validate_json(config_path.read_text("u8")) if config_path.exists() else StickerPackConfig()
        config.update_source = source
        config_path.write_text(json.dumps(config.model_dump(exclude_unset=True), ensure_ascii=False, indent=2), "u8")

    tmp_dir_ctx = TemporaryDirectory() if files_should_download else nullcontext()
    with tmp_dir_ctx as tmp_dir_str:
        tmp_dir = Path(tmp_dir_str) if tmp_dir_str else None
        if tmp_dir:
            async with with_kw_cli(req_kw), with_kw_sem(req_kw):
                await asyncio.gather(*(download(tmp_dir, x) for x in files_should_download))
        with file_updating_ctx():
            if tmp_dir:
                for path in files_should_download:
                    src_p = tmp_dir / path
                    dst_p = pack_path / path
                    dst_p.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(src_p, dst_p)
            after_ops()

    external_fonts_updated = {x.path for x in manifest.external_fonts if x.path in files_should_download}
    logger.info(f"Successfully updated pack `{slug}`")
    return UpdatedResourcesInfo(assets=files_should_download - external_fonts_updated, fonts=external_fonts_updated)
