from pathlib import Path
import hashlib
import json

from astrbot.api import logger

from ..consts import CHECKSUM_FILENAME
from ..sticker_pack import pack_manager
from ..sticker_pack.models import StickerPackManifest
from ..sticker_pack.update import collect_manifest_files


def calc_n_write_checksum(base_path: Path, manifest: StickerPackManifest) -> dict[str, str]:
    files = collect_manifest_files(manifest)
    checksums = [(f, hashlib.sha256((base_path / f).read_bytes()).hexdigest()) for f in files]
    checksum_dict = dict(sorted(checksums, key=lambda x: x[0].split("/")))
    (base_path / CHECKSUM_FILENAME).write_text(json.dumps(checksum_dict, ensure_ascii=False, indent=2), "u8")
    return checksum_dict


def main():
    pack_manager.reload()
    for p in pack_manager.packs:
        calc_n_write_checksum(p.base_path, p.manifest)
        logger.info(f"Wrote {CHECKSUM_FILENAME} in sticker pack `{p.slug}`")
