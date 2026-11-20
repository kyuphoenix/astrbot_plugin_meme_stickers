# Changelog

## v0.2.4

- 彻底排查并修复聊天回复变慢、拖慢机器人和影响其他插件的问题：
  - **接入 `event.stop_event()` 事件阻断**：在指令处理（`/meme-stickers`、`/pjsk`、`/arc`）以及会话命中（选分类、选贴纸、输入文本）后显式调用 `event.stop_event()`，彻底阻止消息穿透传递给大模型（LLM）或其他插件，杜绝后台无谓触发耗时数秒的 AI 回复与群聊双重回复。
  - **非阻塞 Skia 异步线程池渲染**：将 `draw_sticker_grid_from_params`、`draw_sticker_grid_from_packs`、`draw_sticker_pack_grid`、`make_sticker_picture_from_params` 和 `save_image` 等 CPU 密集型绘图操作全部通过 `asyncio.to_thread` 调度到后台工作线程执行，避免占用 Python `asyncio` 主事件循环，彻底消除画图期间整个机器人进程和网络 I/O 冻结卡顿。
  - **指令打断与主动清理**：当用户在会话中输入以 `/`、`!`、`！`、`#`、`.`、`。`、`~` 等开头的指令时，主动清理会话并放行，绝不阻碍用户使用其他插件功能。
  - **死循环防呆与重试限制**：输入无法识别时不再无脑延期 180 秒；连续 2 次无法识别自动销毁会话退出，避免在群聊中被动劫持日常闲聊。
  - **事件监听极速短路**：在 `on_message` 开头增加 `if not self.sessions: return`，无活跃会话时零开销瞬间返回；将监听器优先级提升至 `priority=50` 确保有效会话精准快速响应。
  - **中文自然语言交互支持**：交互指令全面支持 `退出`、`取消`、`算了`、`返回`、`上一级`、`上一步` 等中文关键字。

## v0.2.3

- 升级 Playground 贴纸工坊为「修改后实时画布预览」模式：
  - **实时响应与智能防抖**：监听文字输入、字号滑动、颜色选取、对齐、旋转、描边、坐标偏移、自适应尺寸等所有控件变更，自动防抖触发实时渲染并在画布上呈现最新效果，无需反复手动点击生成。
  - **贴纸切换即时加载**：选择贴纸后立即在右侧画布呈现初始效果，实现“所选即所得”。
  - **并发与时序安全保护**：采用递增请求序列机制，自动丢弃快速键入时延迟到达的陈旧响应，彻底杜绝画面回退与乱序抖动。
  - **实时预览开关**：画布右上角新增「⚡ 实时预览」开关（默认开启），支持自由启闭；提供平滑的微模糊过渡动画，输入体验更加顺滑。
  - **空文字清空支持**：优化后端文字覆盖逻辑，支持清空文字后即时展示纯净底图。

## v0.2.2

- 修复拉取/安装本地贴纸包后 `GET /status` 抛出 `Internal server error` 的问题：
  - 修复 `p.manifest.author` 属性不存在导致的 `AttributeError`（`StickerPackManifest` 模型中无 `author` 字段，改为安全反射访问并默认回退为空字符串）。
  - 为 `web_get_status` 和 `web_get_packs_detail` 增加全局异常拦截保护与详细日志记录，杜绝未捕获异常导致 AstrBot 框架返回 500。
  - 为贴纸包 manifest 信息与分类/贴纸列表解析增加防御性容错，避免个别贴纸包损坏影响整个工作台。
  - 增强 `StickerPack.merged_config`，在 manifest 为空或未加载时不抛异常安全降级。
  - 优化前端 `app.js` 的错误响应解析，遇到非 200 响应时自动提取后端真实报错信息。

## v0.2.1

- 修复空代理配置（`proxy: ""`）导致 httpx 抛出 `ValueError: Unknown scheme for proxy URL URL('')` 的问题。
  - 在 `ConfigModel` 中增加 `proxy` 校验器，自动将空字符串归一化为 `None`。
  - 在 `create_client` 中添加代理参数安全清洗，彻底杜绝拉取 Hub 列表与字体时的空代理异常。
- 修复 AstrBot `PluginRequest` 对象没有 `get_json` 属性导致的解析异常（`'PluginRequest' object has no attribute 'get_json'`）。
  - 实现 `_parse_request_json` 兼容方法，全面支持 `await req.json()`、`req.json` 属性、`req.get_json()` 以及 `req.body` 等多种请求体解析途径。
  - 为所有 Web API 路由处理函数添加灵活传参兼容，确保不同 AstrBot 版本下的分发调度稳定运行。

## v0.2.0

- 新增 AstrBot 官方规范的可视化插件页面（Plugin Page / View: `playground`）：
  - **交互式表情包生成（Playground）**：支持在 WebUI 中可视化联动选择贴纸包、角色/分类、具体贴纸；支持实时调节文字、字号、对齐、颜色、描边、坐标偏移、旋转角度、自动缩放等参数并即时渲染预览；支持一键复制图片与下载保存。
  - **可视化资源管理（Resource Manager）**：直观查看核心字体（Emoji 字体、YurukaFangTang 共享字体）本地状态与体积；支持选择指定镜像源一键拉取 Emoji 字体；可视化查看本地已安装与在线 Hub 贴纸包列表并支持一键安装/更新/重载。
  - **镜像与调试面板（Mirrors & Debug）**：一键切换国内主流镜像源预设，实时查看配置生效状态与操作日志。
- 后端配套注册标准化 Web API（基于 `context.register_web_api` 与 `astrbot.api.web`）。
- 前端集成 AstrBot Bridge SDK（`window.AstrBotPluginView` / `AstrBotPluginPage`），并支持独立调试自动降级。

## v0.1.2

- 配置文件与面板预置多个镜像源选项：
  - 新增 `mirror_preset` 镜像源预设模式，支持 `jsdelivr_mixed` (默认推荐混合加速)、`official` (官方直连)、`ghfast` (ghfast加速镜像)、`ghproxy` (gh-proxy镜像)、`gitmirror` (GitMirror镜像)、`kkgithub` (KKGitHub镜像) 以及 `custom` (完全自定义)。
  - 新增 `emoji_font_url` 配置项，预置 jsDelivr CDN、官方 Tag、ghfast、gh-proxy、gitmirror 等多个候选直链，默认采用 jsDelivr CDN，国内秒级拉取。
  - `hub_manifest_url` 和 `github_url_template` 增加多个预置镜像选项。
- 增强自动 Fallback：字体下载优先使用配置源，若配置源故障会自动按候选列表顺序依次尝试备用镜像，保障高可用性。
- 修复 `update_config` 动态更新配置时模块单例属性同步问题。

## v0.1.1

- 修复初始化阶段因 Google Fonts 官方仓库改组导致的 `NotoColorEmoji.ttf` 404 错误。
- 优化 Emoji 字体下载机制：采用后台异步安全下载，超时时间扩大至 60 秒，避免阻塞 AstrBot 启动与加载失败。
- 增强字体回退机制（Font Fallback）：无本地字体时支持自动回退至系统字体与默认字体，防止极端情况直接抛出 `RuntimeError`。
- 修复 `create_client` 函数传入自定义 `timeout` 或 `proxy` 时触发的 `TypeError` 问题。
- 完善 `/meme-stickers fetch-emoji-font` 手动下载反馈与各指令的容错处理。

## v0.1.0

- 初始发布 AstrBot 版本的 `meme_stickers` 插件。
- 将原 `nonebot-plugin-meme-stickers` 的主要功能迁移到 AstrBot 插件结构中。
- 支持本地与在线贴纸包列表展示。
- 支持在线安装、更新、启用、禁用、删除贴纸包。
- 支持 `/meme-stickers install all` 一次性安装全部在线贴纸包。
- 支持 `pjsk` 与 `arcaea` 贴纸包的交互式制作流程。
- 支持 `/pjsk`、`/arc`、`/arcaea` 快捷进入交互制作。
- 支持 `/meme-stickers generate` 直接生成指定贴纸。
- 支持插件配置项：
  - 是否引用触发消息
  - 交互生成过程中图片格式
  - 最终生成贴纸格式
  - 非 PNG 格式图片质量
- 支持从 AstrBot 数据目录读取贴纸资源与共享字体。
- 支持手动拉取 Emoji 字体资源：`/meme-stickers fetch-emoji-font`
- 支持字体调试命令：`/meme-stickers debug-font <文本>`
- 补充 README、requirements、配置面板 schema 与命令说明。
