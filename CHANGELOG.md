# Changelog

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
