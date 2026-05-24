import asyncio
import json
from pathlib import Path
from typing_extensions import Unpack

from ..consts import CHECKSUM_FILENAME, HUB_MANIFEST_FILENAME, MANIFEST_FILENAME
import hashlib
from ..config import config
from ..utils.file_source import (
    FileSource,
    FileSourceGitHubBranch,
    FileSourceURL,
    ReqKwargs,
    fetch_github_source,
    fetch_source,
    fetch_url_source,
    with_kw_sem,
)
from astrbot.api import logger
from .models import ChecksumDict, HubManifest, HubStickerPackInfo, StickerPackManifest

STICKERS_HUB_FILE_SOURCE = FileSourceGitHubBranch(
    owner="lgc-NB2Dev",
    repo="meme-stickers-hub",
    branch="main",
    path=HUB_MANIFEST_FILENAME,
)


async def fetch_hub(**req_kw: Unpack[ReqKwargs]) -> HubManifest:
    try:
        if config.hub_manifest_url:
            text = (
                await fetch_url_source(
                    FileSourceURL(type="url", url=config.hub_manifest_url),
                    **req_kw,
                )
            ).text
            raw = json.loads(text)
            return [HubStickerPackInfo.model_validate(x) for x in raw]
    except Exception:
        pass
    raw = json.loads((await fetch_github_source(STICKERS_HUB_FILE_SOURCE, **req_kw)).text)
    return [HubStickerPackInfo.model_validate(x) for x in raw]


async def fetch_manifest(source: FileSource, **req_kw: Unpack[ReqKwargs]) -> StickerPackManifest:
    return StickerPackManifest.model_validate_json((await fetch_source(source, MANIFEST_FILENAME, **req_kw)).text)


async def fetch_optional_manifest(source: FileSource, **req_kw: Unpack[ReqKwargs]) -> StickerPackManifest | None:
    try:
        return await fetch_manifest(source, **req_kw)
    except Exception:
        return None


async def fetch_checksum(source: FileSource, **req_kw: Unpack[ReqKwargs]) -> ChecksumDict:
    return json.loads((await fetch_source(source, CHECKSUM_FILENAME, **req_kw)).text)


async def fetch_optional_checksum(source: FileSource, **req_kw: Unpack[ReqKwargs]) -> ChecksumDict | None:
    try:
        return await fetch_checksum(source, **req_kw)
    except Exception:
        return None


async def fetch_hub_and_packs(**req_kw: Unpack[ReqKwargs]) -> tuple[HubManifest, dict[str, StickerPackManifest]]:
    hub = await fetch_hub(**req_kw)
    async with with_kw_sem(req_kw):
        packs = await asyncio.gather(*(fetch_optional_manifest(x.source, **req_kw) for x in hub))
    manifests: dict[str, StickerPackManifest] = {}
    for h, p in zip(hub, packs):
        if p is not None:
            manifests[h.slug] = p
        else:
            logger.warning(f"Hub pack manifest load failed: {h.slug}")
    return hub, manifests


async def temp_sticker_card_params(
    cache_dir: Path,
    hub: HubManifest,
    manifests: dict[str, StickerPackManifest],
    checksums: dict[str, ChecksumDict] | None = None,
    **req_kw: Unpack[ReqKwargs],
) -> list[dict]:
    async def task(i: int, info: HubStickerPackInfo):
        slug = info.slug
        source = info.source
        manifest = manifests[slug]
        sticker = manifest.resolved_sample_sticker.model_copy(deep=True)
        sticker_hash = checksums.get(slug, {}).get(sticker.base_image) if checksums else None
        if (not sticker_hash) or (not (cache_dir / sticker_hash).exists()):
            cache_dir.mkdir(parents=True, exist_ok=True)
            resp = await fetch_source(source, sticker.base_image, **req_kw)
            if not sticker_hash:
                sticker_hash = hashlib.sha256(resp.content).hexdigest()
            (cache_dir / sticker_hash).write_bytes(resp.content)
        sticker.base_image = sticker_hash
        return dict(
            base_path=cache_dir,
            sample_sticker_params=sticker,
            name=manifest.name,
            slug=slug,
            description=manifest.description,
            index=str(i),
        )

    async with with_kw_sem(req_kw):
        return await asyncio.gather(*(task(i, x) for i, x in enumerate(hub, 1)))
