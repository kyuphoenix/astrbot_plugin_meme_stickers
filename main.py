from dataclasses import dataclass
from pathlib import Path
import tempfile
import asyncio
import base64

try:
    from astrbot.api.web import request, json_response, error_response
except ImportError:
    request, json_response, error_response = None, None, None

import skia
import astrbot.api.message_components as Comp
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.all import AstrBotConfig
from astrbot.api.star import Context, Star, StarTools

from .meme_stickers_core.config import set_data_dir, update_config, resolve_color_to_tuple, config as ms_config
from .meme_stickers_core.sticker_pack.manager import StickerPackManager
from .meme_stickers_core.draw.grid import draw_sticker_grid_from_packs, draw_sticker_grid_from_params
from .meme_stickers_core.draw.pack_list import draw_sticker_pack_grid
from .meme_stickers_core.draw.sticker import make_sticker_picture_from_params
from .meme_stickers_core.draw.tools import (
    IMAGE_FORMAT_MAP,
    make_surface_for_picture,
    save_image,
    TEXT_ALIGN_MAP,
    FONT_STYLE_FUNC_MAP,
    get_last_used_font_path,
)
from .meme_stickers_core.sticker_pack.hub import fetch_hub, fetch_hub_and_packs, fetch_checksum, temp_sticker_card_params
from astrbot.api import logger
from .meme_stickers_core.utils.file_source import (
    create_req_sem,
    create_client,
    FileSourceGitHubBranch,
    FileSourceGitHubTag,
    FileSourceURL,
    fetch_github_source,
    fetch_url_source,
)

HELP = """meme-stickers usage:
/meme-stickers help
/meme-stickers list [online|all]
/meme-stickers generate [pack_slug]
/meme-stickers install <slug...|all>
/meme-stickers reload
/meme-stickers update
/meme-stickers delete <pack...>
/meme-stickers enable <pack...>
/meme-stickers disable <pack...>
/meme-stickers debug-font <text>
/meme-stickers fetch-emoji-font
/pjsk
/arc
""".strip()


@dataclass
class SessionState:
    mode: str
    step: str
    pack_slug: str | None = None
    category: str | None = None
    sticker_name: str | None = None
    targets: list[str] | None = None
    expires_at: float = 0.0


class MemeStickersPlugin(Star):
    SESSION_TIMEOUT_SECONDS = 180
    EMOJI_FONT_NAME = "NotoColorEmoji.ttf"

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        update_config(dict(config) if config else None)
        data_dir = StarTools.get_data_dir("astrbot_plugin_meme_stickers")
        set_data_dir(data_dir)

        self.packs_dir = Path(data_dir) / "packs"
        self.packs_dir.mkdir(parents=True, exist_ok=True)
        self.pack_manager = StickerPackManager(self.packs_dir)
        self.sessions: dict[str, SessionState] = {}
        self.bundled_fonts: list[str] = []
        self.PLUGIN_NAME = "astrbot_plugin_meme_stickers"
        self._register_web_apis()

    async def initialize(self):
        self.pack_manager.reload(clear_updating_flags=True)
        self._reload_bundled_fonts()
        shared_dir = self.packs_dir / "_shared"
        target = shared_dir / self.EMOJI_FONT_NAME
        if not (target.exists() and target.stat().st_size > 1024 * 1024):
            asyncio.create_task(self._background_ensure_emoji_font())

    async def _background_ensure_emoji_font(self):
        try:
            logger.info("Emoji 字体未找到，正在后台尝试拉取 (NotoColorEmoji.ttf)...")
            await self._ensure_emoji_font()
            self._reload_bundled_fonts()
            logger.info("Emoji 字体已成功下载并加载")
        except Exception as e:
            logger.warning(
                f"自动拉取 Emoji 字体失败: {e}。这不影响基础贴纸功能，"
                "可在检查网络或配置代理后使用 /meme-stickers fetch-emoji-font 手动下载。"
            )

    async def _ensure_emoji_font(self, force: bool = False, custom_url: str | None = None):
        shared_dir = self.packs_dir / "_shared"
        shared_dir.mkdir(parents=True, exist_ok=True)
        target = shared_dir / self.EMOJI_FONT_NAME
        if not force and target.exists() and target.stat().st_size > 1024 * 1024:
            return

        urls_to_try: list[str] = []
        if custom_url:
            urls_to_try.append(custom_url)
        if getattr(ms_config, "emoji_font_url", None):
            urls_to_try.append(ms_config.emoji_font_url)

        # 预设候选镜像源列表（依次尝试：jsDelivr CDN -> 官方Tag -> 国内镜像）
        default_candidates = [
            "https://cdn.jsdelivr.net/gh/googlefonts/noto-emoji@v2020-09-16-unicode13_1/fonts/NotoColorEmoji.ttf",
            "https://raw.githubusercontent.com/googlefonts/noto-emoji/refs/tags/v2020-09-16-unicode13_1/fonts/NotoColorEmoji.ttf",
            "https://raw.githubusercontent.com/googlefonts/noto-emoji/v2020-09-16-unicode13_1/fonts/NotoColorEmoji.ttf",
            "https://ghfast.top/https://raw.githubusercontent.com/googlefonts/noto-emoji/refs/tags/v2020-09-16-unicode13_1/fonts/NotoColorEmoji.ttf",
            "https://gh-proxy.com/https://raw.githubusercontent.com/googlefonts/noto-emoji/refs/tags/v2020-09-16-unicode13_1/fonts/NotoColorEmoji.ttf",
            "https://raw.gitmirror.com/googlefonts/noto-emoji/refs/tags/v2020-09-16-unicode13_1/fonts/NotoColorEmoji.ttf",
        ]
        for c in default_candidates:
            if c not in urls_to_try:
                urls_to_try.append(c)

        tmp_target = shared_dir / f"{self.EMOJI_FONT_NAME}.tmp"
        last_exc: Exception | None = None
        async with create_client(timeout=60) as cli:
            for url in urls_to_try:
                try:
                    logger.debug(f"尝试拉取 Emoji 字体: {url}")
                    resp = await fetch_url_source(FileSourceURL(type="url", url=url), cli=cli)
                    if len(resp.content) >= 1024 * 1024:
                        tmp_target.write_bytes(resp.content)
                        tmp_target.replace(target)
                        return
                    raise ValueError(f"下载文件过小 ({len(resp.content)} bytes)")
                except Exception as e:
                    last_exc = e
                    tmp_target.unlink(missing_ok=True)
                    logger.debug(f"通过 {url} 下载 Emoji 字体失败 ({e})，尝试下一个候选源...")
                    continue

        if last_exc:
            raise last_exc

    def _reload_bundled_fonts(self):
        shared = self.packs_dir / "_shared"
        primary = shared / "YurukaFangTang.ttf"
        emoji = shared / self.EMOJI_FONT_NAME
        found: list[str] = []
        if primary.exists():
            found.append(str(primary))
        if emoji.exists():
            found.append(str(emoji))
        self.bundled_fonts = found

    def _sid(self, event: AstrMessageEvent) -> str:
        return f"{event.get_group_id()}:{event.get_sender_id()}"

    @staticmethod
    def _now() -> float:
        return asyncio.get_running_loop().time()

    def _new_session(self, **kwargs) -> SessionState:
        return SessionState(expires_at=self._now() + self.SESSION_TIMEOUT_SECONDS, **kwargs)

    def _touch_session(self, st: SessionState):
        st.expires_at = self._now() + self.SESSION_TIMEOUT_SECONDS

    @staticmethod
    def _is_exit(txt: str) -> bool:
        return txt.lower() in {"0", "q", "quit", "exit", "cancel"}

    @staticmethod
    def _is_back(txt: str) -> bool:
        return txt.lower() in {"r", "b", "back", "return"}

    async def _send_image(self, event: AstrMessageEvent, data: bytes, suffix: str, ext: str = "jpg"):
        p = Path(tempfile.gettempdir()) / f"meme_{suffix}_{id(event)}.{ext}"
        p.write_bytes(data)
        try:
            if bool(getattr(ms_config, "quote_reply", False)):
                reply = Comp.Reply(id=event.message_obj.message_id)
                img = Comp.Image.fromFileSystem(str(p))
                yield event.chain_result([reply, img])
                return
            yield event.image_result(str(p))
        finally:
            p.unlink(missing_ok=True)

    def _plain(self, event: AstrMessageEvent, text: str):
        if bool(getattr(ms_config, "quote_reply", False)):
            reply = Comp.Reply(id=event.message_obj.message_id)
            return event.chain_result([reply, Comp.Plain(text)])
        return event.plain_result(text)

    @staticmethod
    def _parse_generate_args(tokens: list[str]) -> tuple[dict, list[str]]:
        opts, text_parts = {}, []
        i = 0
        while i < len(tokens):
            t = tokens[i]
            if t in {"-A", "--auto-resize", "-N", "--no-auto-resize", "-D", "--debug"}:
                opts[t] = True
                i += 1
                continue
            if t in {
                "-x", "--x", "-y", "--y", "-a", "--align", "-r", "--rotate", "-c", "--color",
                "-C", "--stroke-color", "-W", "--stroke-width-factor", "-s", "--font-size",
                "-S", "--font-style", "-f", "--image-format", "-b", "--background",
            } and i + 1 < len(tokens):
                opts[t] = tokens[i + 1]
                i += 2
                continue
            text_parts.append(t)
            i += 1
        return opts, text_parts

    async def _start_pack_interactive(self, event: AstrMessageEvent, pack_query: str):
        pack = self.pack_manager.find_pack(pack_query)
        if not pack:
            yield self._plain(event, f"未找到贴纸包: {pack_query}")
            return
        if pack.unavailable:
            yield self._plain(event, f"贴纸包不可用: {pack_query}")
            return

        self.sessions[self._sid(event)] = self._new_session(
            mode="generate",
            step="pick_category",
            pack_slug=pack.slug,
        )
        categories = sorted(pack.manifest.resolved_stickers_by_category.keys())
        sample = [
            pack.manifest.resolved_stickers_by_category[c][0].params.model_copy(
                update={"text": f"{i}. {c}"}
            )
            for i, c in enumerate(categories, 1)
        ]
        for s in sample:
            s.font_families = [*self.bundled_fonts, *s.font_families]
        img = save_image(
            draw_sticker_grid_from_params(
                pack.manifest.sticker_grid.resolved_category_params,
                sample,
                pack.base_path,
            ),
            IMAGE_FORMAT_MAP.get(ms_config.interactive_preview_image_format, skia.kJPEG),
            quality=ms_config.non_png_quality
            if ms_config.interactive_preview_image_format != "png"
            else 100,
        )
        async for r in self._send_image(event, img, f"pick_category_{pack.slug}"):
            yield r
        yield self._plain(
            event,
            f"已进入 {pack.slug} 交互式制作，请输入分类名称或序号（输入 r 返回，0 退出）",
        )

    @filter.command("meme-stickers", alias={"stickers"})
    async def meme_stickers(self, event: AstrMessageEvent):
        """管理贴纸包、查看列表、安装资源，并支持按指定贴纸直接生成表情包。"""
        parts = event.get_message_str().strip().split()
        args = parts[1:] if len(parts) > 1 else []
        if not args or args[0] in {"help", "-h", "--help"}:
            yield self._plain(event,HELP)
            return

        sub = args[0].lower()
        if sub == "list":
            mode = args[1].lower() if len(args) > 1 else ""
            if mode == "online":
                hub, manifests = await fetch_hub_and_packs()
                if not manifests:
                    yield self._plain(event, "Hub 上无可用贴纸包")
                    return
                sem = create_req_sem()
                checksums = dict(
                    zip((x.slug for x in hub), await asyncio.gather(*(fetch_checksum(x.source, sem=sem) for x in hub)))
                )
                preview_cache = Path(StarTools.get_data_dir("astrbot_plugin_meme_stickers")) / "_preview_cache"
                params = await temp_sticker_card_params(preview_cache, hub, manifests, checksums)
                img = save_image(
                    draw_sticker_pack_grid(params),
                    IMAGE_FORMAT_MAP.get(ms_config.interactive_preview_image_format, skia.kJPEG),
                    quality=ms_config.non_png_quality if ms_config.interactive_preview_image_format != "png" else 100,
                )
                async for r in self._send_image(event, img, "list_online"):
                    yield r
                yield self._plain(event, "以上为 Hub 中可用的贴纸包列表")
                return

            packs = self.pack_manager.packs if mode == "all" else self.pack_manager.available_packs
            if not packs:
                yield self._plain(event, "当前无可用贴纸包")
                return
            img = save_image(
                draw_sticker_grid_from_packs(packs),
                IMAGE_FORMAT_MAP.get(ms_config.interactive_preview_image_format, skia.kJPEG),
                quality=ms_config.non_png_quality if ms_config.interactive_preview_image_format != "png" else 100,
            )
            async for r in self._send_image(event, img, "list"):
                yield r
            return

        if sub == "reload":
            op = self.pack_manager.reload(clear_updating_flags=True)
            try:
                await self._ensure_emoji_font()
            except Exception as e:
                logger.warning(f"重载时检查 Emoji 字体失败: {e}")
            self._reload_bundled_fonts()
            yield self._plain(event, f"已重载，成功 {len(op.succeed)}，失败 {len(op.failed)}")
            return

        if sub == "update":
            op, _ = await self.pack_manager.update_all(force=False)
            try:
                await self._ensure_emoji_font()
            except Exception as e:
                logger.warning(f"更新时检查 Emoji 字体失败: {e}")
            self._reload_bundled_fonts()
            yield self._plain(event, f"更新完成：成功 {len(op.succeed)}，跳过 {len(op.skipped)}，失败 {len(op.failed)}")
            return

        if sub == "install":
            hub = await fetch_hub()
            slugs = set(args[1:])
            if "all" in slugs:
                infos = list(hub)
            else:
                infos = [x for x in hub if x.slug in slugs]
            if not infos:
                yield self._plain(event, "未找到可安装的贴纸包")
                return
            op, _ = await self.pack_manager.install(infos)
            try:
                await self._ensure_emoji_font()
            except Exception as e:
                logger.warning(f"安装时检查 Emoji 字体失败: {e}")
            self._reload_bundled_fonts()
            yield self._plain(event, f"安装完成：成功 {len(op.succeed)}，跳过 {len(op.skipped)}，失败 {len(op.failed)}")
            return

        if sub == "debug-font":
            text = " ".join(args[1:]).strip() if len(args) > 1 else "Font Debug 123"
            packs = self.pack_manager.available_packs
            if not packs:
                yield self._plain(event, "当前无可用贴纸包")
                return
            pack = packs[0]
            sticker = pack.manifest.resolved_sample_sticker
            params = sticker.model_copy(deep=True)
            params.text = text
            params.font_families = [*self.bundled_fonts, *params.font_families]
            pic = make_sticker_picture_from_params(pack.base_path, params, auto_resize=True)
            img = save_image(
                make_surface_for_picture(pic, None),
                IMAGE_FORMAT_MAP.get(ms_config.interactive_preview_image_format, skia.kJPEG),
                quality=ms_config.non_png_quality if ms_config.interactive_preview_image_format != "png" else 100,
            )
            async for r in self._send_image(event, img, "debug_font"):
                yield r
            attempted = self.bundled_fonts[0] if self.bundled_fonts else "(none)"
            # Current rendering path in sticker.py uses direct Typeface.MakeFromFile.
            actual = attempted if attempted != "(none)" else "(fallback/system)"
            yield self._plain(event,
                "debug-font result:\\n"
                f"attempted_font_path: {attempted}\\n"
                f"actual_used_font_path: {actual}\\n"
                f"emoji_font_path: {self.packs_dir / '_shared' / self.EMOJI_FONT_NAME}"
            )
            return

        if sub == "fetch-emoji-font":
            p = self.packs_dir / "_shared" / self.EMOJI_FONT_NAME
            force = any(x in args for x in ("force", "-f", "--force"))
            yield self._plain(event, "正在尝试下载 Emoji 字体，请稍候...")
            try:
                await self._ensure_emoji_font(force=force)
                self._reload_bundled_fonts()
                size_mb = p.stat().st_size / (1024 * 1024) if p.exists() else 0
                yield self._plain(
                    event,
                    f"Emoji 字体获取成功！\n路径: {p}\n文件大小: {size_mb:.2f} MB"
                )
            except Exception as e:
                yield self._plain(
                    event,
                    f"Emoji 字体获取失败: {type(e).__name__}: {e}\n"
                    "提示：如果在国内 Docker 运行，请检查容器网络或配置 proxy 后重试。"
                )
            return

        if sub in {"delete", "enable", "disable"}:
            if len(args) < 2:
                yield self._plain(event, f"用法: /meme-stickers {sub} <pack...>")
                return
            self.sessions[self._sid(event)] = self._new_session(mode=sub, step="confirm_manage", targets=args[1:])
            yield self._plain(event, f"确认 {sub} 以下贴纸包？{', '.join(args[1:])}\n输入 y 确认，其他内容取消")
            return

        if sub == "generate":
            if len(args) == 1:
                packs = self.pack_manager.available_packs
                if not packs:
                    yield self._plain(event, "当前无可用贴纸包")
                    return
                self.sessions[self._sid(event)] = self._new_session(mode="generate", step="pick_pack")
                img = save_image(
                    draw_sticker_grid_from_packs(packs),
                    IMAGE_FORMAT_MAP.get(ms_config.interactive_preview_image_format, skia.kJPEG),
                    quality=ms_config.non_png_quality if ms_config.interactive_preview_image_format != "png" else 100,
                )
                async for r in self._send_image(event, img, "pick_pack"):
                    yield r
                yield self._plain(event, "请输入贴纸包序号、slug 或名称（输入 0 退出）")
                return

            if len(args) < 4:
                yield self._plain(event, "用法: /meme-stickers generate <pack_slug> <贴纸名> <文本>")
                return

            pack = self.pack_manager.find_pack(args[1])
            if not pack:
                yield self._plain(event, f"未找到贴纸包: {args[1]}")
                return
            sticker = pack.manifest.find_sticker_by_name(args[2])
            if not sticker:
                yield self._plain(event, f"未找到贴纸: {args[2]}")
                return

            opts, extra = self._parse_generate_args(args[3:])
            txt = " ".join(extra).strip() or sticker.params.text
            params = sticker.params.model_copy(deep=True)
            params.text = txt
            params.font_families = [*self.bundled_fonts, *params.font_families]

            if "-x" in opts or "--x" in opts:
                params.text_x = float(opts.get("-x", opts.get("--x")))
            if "-y" in opts or "--y" in opts:
                params.text_y = float(opts.get("-y", opts.get("--y")))
            if "-a" in opts or "--align" in opts:
                av = opts.get("-a", opts.get("--align"))
                if av in TEXT_ALIGN_MAP:
                    params.text_align = av
            if "-r" in opts or "--rotate" in opts:
                params.text_rotate_degrees = float(opts.get("-r", opts.get("--rotate")))
            if "-c" in opts or "--color" in opts:
                params.text_color = resolve_color_to_tuple(opts.get("-c", opts.get("--color")))
            if "-C" in opts or "--stroke-color" in opts:
                params.stroke_color = resolve_color_to_tuple(opts.get("-C", opts.get("--stroke-color")))
            if "-W" in opts or "--stroke-width-factor" in opts:
                params.stroke_width_factor = float(opts.get("-W", opts.get("--stroke-width-factor")))
            if "-s" in opts or "--font-size" in opts:
                params.font_size = float(opts.get("-s", opts.get("--font-size")))
            if "-S" in opts or "--font-style" in opts:
                sv = opts.get("-S", opts.get("--font-style"))
                if sv in FONT_STYLE_FUNC_MAP:
                    params.font_style = sv

            image_format = opts.get("-f", opts.get("--image-format", ms_config.final_sticker_image_format))
            auto_resize = ("-A" in opts or "--auto-resize" in opts) or not ("-N" in opts or "--no-auto-resize")
            debug = ("-D" in opts or "--debug" in opts)

            bg = None
            if image_format == "jpeg":
                bv = opts.get("-b", opts.get("--background"))
                bg = skia.Color(*resolve_color_to_tuple(bv)) if bv else ms_config.default_sticker_background

            pic = make_sticker_picture_from_params(pack.base_path, params, auto_resize=auto_resize, debug=debug)
            img = save_image(
                make_surface_for_picture(pic, bg),
                IMAGE_FORMAT_MAP.get(image_format, skia.kPNG),
                quality=ms_config.non_png_quality if image_format != "png" else 100,
            )
            async for r in self._send_image(event, img, "gen"):
                yield r
            return

        yield self._plain(event, "未知子命令，请使用 /meme-stickers help")

    @filter.command("pjsk")
    async def pjsk_cmd(self, event: AstrMessageEvent):
        """进入 Project Sekai 贴纸包的交互式制作流程。"""
        async for r in self._start_pack_interactive(event, "pjsk"):
            yield r

    @filter.command("arc", alias={"arcaea"})
    async def arc_cmd(self, event: AstrMessageEvent):
        """进入 Arcaea 贴纸包的交互式制作流程。"""
        async for r in self._start_pack_interactive(event, "arcaea"):
            yield r

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        sid = self._sid(event)
        st = self.sessions.get(sid)
        if not st:
            return

        txt = event.get_message_str().strip()
        if not txt:
            return
        if txt.startswith("/"):
            return
        if txt.lower() in {"pjsk", "arc", "arcaea", "meme-stickers", "stickers"}:
            return

        if st.expires_at and self._now() > st.expires_at:
            self.sessions.pop(sid, None)
            return
        self._touch_session(st)

        if self._is_exit(txt):
            self.sessions.pop(sid, None)
            yield self._plain(event, "已退出操作")
            return

        if st.step == "confirm_manage":
            if txt.lower() != "y":
                self.sessions.pop(sid, None)
                yield self._plain(event, "已取消操作")
                return
            ok, fail = 0, 0
            for q in st.targets or []:
                pack = self.pack_manager.find_pack(q, include_unavailable=True)
                if not pack:
                    fail += 1
                    continue
                try:
                    if st.mode == "delete":
                        pack.delete()
                    elif st.mode == "enable":
                        pack.config.disabled = False
                        pack.save_config()
                    elif st.mode == "disable":
                        pack.config.disabled = True
                        pack.save_config()
                    ok += 1
                except Exception:
                    fail += 1
            self.sessions.pop(sid, None)
            yield self._plain(event, f"{st.mode} 完成：成功 {ok}，失败 {fail}")
            return

        if st.step == "pick_pack":
            packs = self.pack_manager.available_packs
            pack = None
            if txt.isdigit() and 1 <= int(txt) <= len(packs):
                pack = packs[int(txt) - 1]
            if not pack:
                pack = self.pack_manager.find_pack(txt)
            if not pack:
                yield self._plain(event, "未找到贴纸包，请重新输入")
                return
            st.pack_slug = pack.slug
            st.step = "pick_category"
            categories = sorted(pack.manifest.resolved_stickers_by_category.keys())
            sample = [
                pack.manifest.resolved_stickers_by_category[c][0].params.model_copy(update={"text": f"{i}. {c}"})
                for i, c in enumerate(categories, 1)
            ]
            for s in sample:
                s.font_families = [*self.bundled_fonts, *s.font_families]
            img = save_image(
                draw_sticker_grid_from_params(pack.manifest.sticker_grid.resolved_category_params, sample, pack.base_path),
                IMAGE_FORMAT_MAP.get(ms_config.interactive_preview_image_format, skia.kJPEG),
                quality=ms_config.non_png_quality if ms_config.interactive_preview_image_format != "png" else 100,
            )
            async for r in self._send_image(event, img, "pick_category"):
                yield r
            yield self._plain(event, "请输入分类名称或序号（输入 r 返回）")
            return

        if st.step == "pick_category":
            pack = self.pack_manager.find_pack(st.pack_slug or "")
            if not pack:
                self.sessions.pop(sid, None)
                yield self._plain(event, "贴纸包不可用，操作结束")
                return
            if self._is_back(txt):
                st.step = "pick_pack"
                yield self._plain(event, "已返回贴纸包选择，请输入贴纸包序号、slug 或名称")
                return

            categories = sorted(pack.manifest.resolved_stickers_by_category.keys())
            c = None
            if txt.isdigit() and 1 <= int(txt) <= len(categories):
                c = categories[int(txt) - 1]
            if not c:
                c = next((x for x in categories if x.lower() == txt.lower()), None)
            if not c:
                yield self._plain(event, "未找到分类，请重新输入")
                return

            st.category = c
            stickers = pack.manifest.resolved_stickers_by_category[c]
            if len(stickers) == 1:
                st.sticker_name = stickers[0].name
                st.step = "input_text"
                yield self._plain(event, "该分类只有一个贴纸，请直接输入要添加的文本")
                return

            st.step = "pick_sticker"
            preview = [x.params.model_copy(update={"text": f"{i}. {x.name}"}) for i, x in enumerate(stickers, 1)]
            gp = pack.manifest.sticker_grid.resolved_stickers_params.get(c, pack.manifest.sticker_grid.default_params)
            for s in preview:
                s.font_families = [*self.bundled_fonts, *s.font_families]
            img = save_image(
                draw_sticker_grid_from_params(gp, preview, pack.base_path),
                IMAGE_FORMAT_MAP.get(ms_config.interactive_preview_image_format, skia.kJPEG),
                quality=ms_config.non_png_quality if ms_config.interactive_preview_image_format != "png" else 100,
            )
            async for r in self._send_image(event, img, "pick_sticker"):
                yield r
            yield self._plain(event, "请输入贴纸名称或序号（输入 r 返回分类）")
            return

        if st.step == "pick_sticker":
            pack = self.pack_manager.find_pack(st.pack_slug or "")
            if not pack:
                self.sessions.pop(sid, None)
                yield self._plain(event, "贴纸包不可用，操作结束")
                return
            if self._is_back(txt):
                st.step = "pick_category"
                yield self._plain(event, "已返回分类选择，请输入分类名称或序号")
                return

            stickers = pack.manifest.resolved_stickers_by_category.get(st.category or "", [])
            sticker = None
            if txt.isdigit() and 1 <= int(txt) <= len(stickers):
                sticker = stickers[int(txt) - 1]
            if not sticker:
                sticker = next((x for x in stickers if x.name.lower() == txt.lower()), None)
            if not sticker:
                yield self._plain(event, "未找到贴纸，请重新输入")
                return

            st.sticker_name = sticker.name
            st.step = "input_text"
            yield self._plain(event, "请输入贴纸文本")
            return

        if st.step == "input_text":
            pack = self.pack_manager.find_pack(st.pack_slug or "")
            if not pack:
                self.sessions.pop(sid, None)
                yield self._plain(event, "贴纸包不可用，操作结束")
                return
            sticker = pack.manifest.find_sticker_by_name(st.sticker_name or "")
            if not sticker:
                self.sessions.pop(sid, None)
                yield self._plain(event, "贴纸不可用，操作结束")
                return
            user_text = txt.strip()
            if not user_text:
                return

            params = sticker.params.model_copy(deep=True)
            params.text = user_text
            params.font_families = [*self.bundled_fonts, *params.font_families]

            image_format = ms_config.final_sticker_image_format
            bg = ms_config.default_sticker_background if image_format == "jpeg" else None
            pic = make_sticker_picture_from_params(pack.base_path, params, auto_resize=True)
            img = save_image(
                make_surface_for_picture(pic, bg),
                IMAGE_FORMAT_MAP.get(image_format, skia.kPNG),
                quality=ms_config.non_png_quality if image_format != "png" else 100,
            )
            try:
                async for r in self._send_image(event, img, "interactive"):
                    yield r
            finally:
                self.sessions.pop(sid, None)



    def _register_web_apis(self):
        if not hasattr(self.context, "register_web_api"):
            return
        apis = [
            (f"/{self.PLUGIN_NAME}/status", self.web_get_status, ["GET"], "获取插件与字体状态"),
            (f"/{self.PLUGIN_NAME}/hub", self.web_get_hub, ["GET"], "获取在线Hub贴纸包"),
            (f"/{self.PLUGIN_NAME}/packs", self.web_get_packs_detail, ["GET"], "获取已安装贴纸包详情树"),
            (f"/{self.PLUGIN_NAME}/install", self.web_install_pack, ["POST"], "安装贴纸包"),
            (f"/{self.PLUGIN_NAME}/reload", self.web_reload_packs, ["POST"], "重载贴纸包"),
            (f"/{self.PLUGIN_NAME}/fetch_emoji_font", self.web_fetch_emoji_font, ["POST"], "拉取Emoji字体"),
            (f"/{self.PLUGIN_NAME}/generate", self.web_generate, ["POST"], "Playground生成贴纸图片"),
            (f"/{self.PLUGIN_NAME}/switch_mirror", self.web_switch_mirror, ["POST"], "切换镜像源预设"),
        ]
        for route, handler, methods, desc in apis:
            try:
                self.context.register_web_api(route, handler, methods, desc)
            except Exception as e:
                logger.warning(f"注册 Web API {route} 失败: {e}")

    @staticmethod
    async def _parse_request_json(req):
        if req is None:
            return {}
        if hasattr(req, "json"):
            j = getattr(req, "json")
            if callable(j):
                try:
                    res = j()
                    if asyncio.iscoroutine(res):
                        res = await res
                    if isinstance(res, dict):
                        return res
                except Exception:
                    pass
            elif isinstance(j, dict):
                return j
        if hasattr(req, "get_json"):
            gj = getattr(req, "get_json")
            if callable(gj):
                try:
                    res = gj()
                    if asyncio.iscoroutine(res):
                        res = await res
                    if isinstance(res, dict):
                        return res
                except Exception:
                    pass
        for attr in ("body", "data", "_body"):
            if hasattr(req, attr):
                val = getattr(req, attr)
                if isinstance(val, (bytes, str)):
                    import json
                    try:
                        res = json.loads(val)
                        if isinstance(res, dict):
                            return res
                    except Exception:
                        pass
                elif isinstance(val, dict):
                    return val
        return {}

    @staticmethod
    def _safe_color_parse(c):
        if isinstance(c, (list, tuple)) and len(c) in (3, 4):
            r, g, b = int(c[0]), int(c[1]), int(c[2])
            a = int(c[3]) if len(c) == 4 else 255
            return (r, g, b, a)
        return resolve_color_to_tuple(str(c))

    async def web_get_status(self, *args, **kwargs):
        shared_dir = self.packs_dir / "_shared"
        emoji_p = shared_dir / self.EMOJI_FONT_NAME
        primary_p = shared_dir / "YurukaFangTang.ttf"
        
        packs_data = []
        for p in self.pack_manager.packs:
            packs_data.append({
                "slug": p.slug,
                "name": p.manifest.name if p.manifest else p.slug,
                "author": p.manifest.author if p.manifest else "",
                "description": p.manifest.description if p.manifest else "",
                "version": p.manifest.version if p.manifest else "",
                "stickers_count": len(p.manifest.stickers) if p.manifest else 0,
                "categories": list(p.manifest.resolved_stickers_by_category.keys()) if p.manifest else [],
                "disabled": p.config.disabled,
                "unavailable": p.unavailable,
            })
            
        return json_response({
            "status": "ok",
            "data": {
                "installed_packs": packs_data,
                "total_packs": len(packs_data),
                "available_packs_count": len(self.pack_manager.available_packs),
                "emoji_font": {
                    "name": self.EMOJI_FONT_NAME,
                    "exists": emoji_p.exists(),
                    "size": emoji_p.stat().st_size if emoji_p.exists() else 0,
                    "size_mb": round(emoji_p.stat().st_size / (1024 * 1024), 2) if emoji_p.exists() else 0,
                    "path": str(emoji_p),
                },
                "primary_font": {
                    "name": "YurukaFangTang.ttf",
                    "exists": primary_p.exists(),
                    "size": primary_p.stat().st_size if primary_p.exists() else 0,
                    "path": str(primary_p),
                },
                "config": {
                    "mirror_preset": getattr(ms_config, "mirror_preset", "jsdelivr_mixed"),
                    "emoji_font_url": getattr(ms_config, "emoji_font_url", ""),
                    "hub_manifest_url": getattr(ms_config, "hub_manifest_url", ""),
                    "github_url_template": getattr(ms_config, "github_url_template", ""),
                    "proxy": getattr(ms_config, "proxy", "") or "",
                },
                "bundled_fonts": self.bundled_fonts,
            }
        })

    async def web_get_hub(self, *args, **kwargs):
        try:
            hub = await fetch_hub()
            installed_slugs = {p.slug for p in self.pack_manager.packs}
            items = []
            for h in hub:
                items.append({
                    "slug": h.slug,
                    "installed": h.slug in installed_slugs,
                    "source": h.source.model_dump() if hasattr(h.source, "model_dump") else str(h.source),
                })
            return json_response({"status": "ok", "data": items})
        except Exception as e:
            return error_response(f"获取在线 Hub 列表失败: {e}", status_code=500)

    async def web_install_pack(self, *args, **kwargs):
        try:
            req = kwargs.get("request") or (args[0] if args else request)
            body = await self._parse_request_json(req)
            slugs = body.get("slugs", [])
            install_all = body.get("all", False)
            hub = await fetch_hub()
            if install_all:
                infos = list(hub)
            else:
                infos = [x for x in hub if x.slug in slugs]
            if not infos:
                return error_response("未匹配到可安装的贴纸包", status_code=400)
            
            op, _ = await self.pack_manager.install(infos)
            try:
                await self._ensure_emoji_font()
            except Exception as e:
                logger.warning(f"安装贴纸包后检查 Emoji 字体失败: {e}")
            self._reload_bundled_fonts()
            return json_response({
                "status": "ok",
                "data": {
                    "succeed": [str(x) for x in op.succeed],
                    "failed": [f"{x.target}: {x.exc}" for x in op.failed],
                    "skipped": [str(x) for x in op.skipped],
                }
            })
        except Exception as e:
            return error_response(f"安装贴纸包出错: {e}", status_code=500)

    async def web_reload_packs(self, *args, **kwargs):
        try:
            op = self.pack_manager.reload(clear_updating_flags=True)
            try:
                await self._ensure_emoji_font()
            except Exception as e:
                logger.warning(f"重载时检查 Emoji 字体失败: {e}")
            self._reload_bundled_fonts()
            return json_response({
                "status": "ok",
                "data": {
                    "succeed": len(op.succeed),
                    "failed": len(op.failed),
                    "total": len(self.pack_manager.packs),
                }
            })
        except Exception as e:
            return error_response(f"重载失败: {e}", status_code=500)

    async def web_fetch_emoji_font(self, *args, **kwargs):
        try:
            req = kwargs.get("request") or (args[0] if args else request)
            body = await self._parse_request_json(req)
            force = body.get("force", True)
            custom_url = body.get("url")
            await self._ensure_emoji_font(force=force, custom_url=custom_url)
            self._reload_bundled_fonts()
            p = self.packs_dir / "_shared" / self.EMOJI_FONT_NAME
            return json_response({
                "status": "ok",
                "data": {
                    "path": str(p),
                    "exists": p.exists(),
                    "size": p.stat().st_size if p.exists() else 0,
                    "size_mb": round(p.stat().st_size / (1024 * 1024), 2) if p.exists() else 0,
                }
            })
        except Exception as e:
            return error_response(f"下载 Emoji 字体失败: {e}", status_code=500)

    async def web_get_packs_detail(self, *args, **kwargs):
        packs_tree = {}
        for pack in self.pack_manager.available_packs:
            if not pack.manifest:
                continue
            cat_dict = {}
            for cat_name, stickers in pack.manifest.resolved_stickers_by_category.items():
                cat_dict[cat_name] = [
                    {
                        "name": s.name,
                        "text": s.params.text,
                        "width": s.params.width,
                        "height": s.params.height,
                        "text_x": s.params.text_x,
                        "text_y": s.params.text_y,
                        "text_align": s.params.text_align,
                        "text_rotate_degrees": s.params.text_rotate_degrees,
                        "text_color": [s.params.text_color[0], s.params.text_color[1], s.params.text_color[2], s.params.text_color[3]],
                        "stroke_color": [s.params.stroke_color[0], s.params.stroke_color[1], s.params.stroke_color[2], s.params.stroke_color[3]],
                        "stroke_width_factor": s.params.stroke_width_factor,
                        "font_size": s.params.font_size,
                        "font_style": s.params.font_style,
                    }
                    for s in stickers
                ]
            packs_tree[pack.slug] = {
                "name": pack.manifest.name,
                "categories": cat_dict,
            }
        return json_response({"status": "ok", "data": packs_tree})

    async def web_generate(self, *args, **kwargs):
        try:
            req = kwargs.get("request") or (args[0] if args else request)
            body = await self._parse_request_json(req)
            pack_slug = body.get("pack_slug")
            sticker_name = body.get("sticker_name")
            text = body.get("text", "")
            
            pack = self.pack_manager.find_pack(pack_slug)
            if not pack or pack.unavailable or not pack.manifest:
                return error_response(f"贴纸包不可用或未找到: {pack_slug}", status_code=404)
            sticker = pack.manifest.find_sticker_by_name(sticker_name)
            if not sticker:
                return error_response(f"贴纸未找到: {sticker_name}", status_code=404)
                
            params = sticker.params.model_copy(deep=True)
            params.text = text if text != "" else sticker.params.text
            params.font_families = [*self.bundled_fonts, *params.font_families]
            
            if "text_x" in body and body["text_x"] is not None:
                params.text_x = float(body["text_x"])
            if "text_y" in body and body["text_y"] is not None:
                params.text_y = float(body["text_y"])
            if "text_align" in body and body["text_align"] in TEXT_ALIGN_MAP:
                params.text_align = body["text_align"]
            if "text_rotate_degrees" in body and body["text_rotate_degrees"] is not None:
                params.text_rotate_degrees = float(body["text_rotate_degrees"])
            if "text_color" in body and body["text_color"]:
                params.text_color = self._safe_color_parse(body["text_color"])
            if "stroke_color" in body and body["stroke_color"]:
                params.stroke_color = self._safe_color_parse(body["stroke_color"])
            if "stroke_width_factor" in body and body["stroke_width_factor"] is not None:
                params.stroke_width_factor = float(body["stroke_width_factor"])
            if "font_size" in body and body["font_size"] is not None:
                params.font_size = float(body["font_size"])
            if "font_style" in body and body["font_style"] in FONT_STYLE_FUNC_MAP:
                params.font_style = body["font_style"]
                
            auto_resize = body.get("auto_resize", True)
            debug = body.get("debug", False)
            image_format = body.get("image_format", "png")
            bg = None
            if image_format == "jpeg":
                bv = body.get("background")
                bg = skia.Color(*self._safe_color_parse(bv)) if bv else ms_config.default_sticker_background

            pic = make_sticker_picture_from_params(pack.base_path, params, auto_resize=auto_resize, debug=debug)
            img_bytes = save_image(
                make_surface_for_picture(pic, bg),
                IMAGE_FORMAT_MAP.get(image_format, skia.kPNG),
                quality=ms_config.non_png_quality if image_format != "png" else 100,
            )
            
            img_b64 = base64.b64encode(img_bytes).decode("ascii")
            mime = f"image/{image_format if image_format != 'jpeg' else 'jpeg'}"
            data_uri = f"data:{mime};base64,{img_b64}"
            
            return json_response({
                "status": "ok",
                "data": {
                    "data_uri": data_uri,
                    "width": params.width,
                    "height": params.height,
                    "format": image_format,
                    "size_bytes": len(img_bytes),
                }
            })
        except Exception as e:
            return error_response(f"生成表情包失败: {e}", status_code=500)

    async def web_switch_mirror(self, *args, **kwargs):
        try:
            req = kwargs.get("request") or (args[0] if args else request)
            body = await self._parse_request_json(req)
            preset = body.get("preset")
            if not preset:
                return error_response("缺少 preset 参数", status_code=400)
            update_config({"mirror_preset": preset})
            return json_response({
                "status": "ok",
                "data": {
                    "mirror_preset": ms_config.mirror_preset,
                    "emoji_font_url": ms_config.emoji_font_url,
                    "hub_manifest_url": ms_config.hub_manifest_url,
                    "github_url_template": ms_config.github_url_template,
                }
            })
        except Exception as e:
            return error_response(f"切换镜像源失败: {e}", status_code=500)
