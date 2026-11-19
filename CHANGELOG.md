# Changelog

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
