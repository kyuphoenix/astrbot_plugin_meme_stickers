# astrbot_plugin_meme_stickers

本插件由 [lgc-NB2Dev/nonebot-plugin-meme-stickers](https://github.com/lgc-NB2Dev/nonebot-plugin-meme-stickers) 迁移而来，面向 AstrBot 运行环境重构。

## 插件信息

- 插件名：`astrbot_plugin_meme_stickers`
- AstrBot 显示名：`Arc/pjsk表情包制作`
- 主要能力：
  - 贴纸包列表（本地/在线）
  - 在线安装与更新贴纸包
  - 交互式制作贴纸（包 -> 分类 -> 贴纸 -> 文本）
  - 快捷指令直达制作流程（`pjsk` / `arc`）

## 使用方法

### 基础指令

- `/meme-stickers help`
- `/meme-stickers list`
- `/meme-stickers list all`
- `/meme-stickers list online`
- `/meme-stickers install <slug...>`
- `/meme-stickers update`
- `/meme-stickers reload`
- `/meme-stickers generate`

### 快捷制作指令

- `pjsk`：直接进入 `pjsk` 贴纸包交互式制作
- `arc` 或 `arcaea`：直接进入 `arcaea` 贴纸包交互式制作

### 交互说明

- 输入 `r` / `b` / `back` / `return`：返回上一步
- 输入 `0` / `q` / `quit` / `exit` / `cancel`：退出当前交互
- 会话为静默超时，超时后自动失效（不额外提示）

## 资源与字体

- 贴纸资源目录（AstrBot 数据目录下）：`plugin_data/astrbot_plugin_meme_stickers/packs/`
- 已安装贴纸包示例：
  - `packs/pjsk/`
  - `packs/arcaea/`
- 共享字体目录：`packs/_shared/`

插件会从上述存储目录读取字体，不依赖插件目录内置字体。

## 安装与打包

1. 将 `astrbot_plugin_meme_stickers` 文件夹打包为 zip。
2. zip 顶层必须是插件文件夹本身（不能直接把 `main.py` 放在根目录）。
3. 在 AstrBot 插件管理页面上传安装。

## 依赖

见同目录下 `requirements.txt`。
