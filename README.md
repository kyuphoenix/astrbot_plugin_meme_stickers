# astrbot_plugin_meme_stickers

Meme Stickers 的 AstrBot 重构版插件。

## 功能

- 贴纸包列表：`/meme-stickers list`
- 在线列表：`/meme-stickers list online`
- 显示全部（含不可用）：`/meme-stickers list all`
- 生成贴纸：`/meme-stickers generate`
- 管理命令：`install / reload / update / delete / enable / disable`
- 支持交互式选择（贴纸包/分类/贴纸/文本）
- 支持高级参数（位置、旋转、颜色、字体样式、输出格式等）

## 安装说明

1. 将 `astrbot_plugin_meme_stickers` 文件夹整体打包为 zip。
2. 上传到 AstrBot 插件管理页面安装。
3. 确保 zip 顶层是插件文件夹本身，不要把 `main.py` 直接放在压缩包根目录。

## 字体

插件优先使用自身目录下 `fonts/` 中的字体文件（`.ttf/.otf/.ttc`）。

## 说明

- 本插件已移除对外部 `nonebot` / `cookit` 包的运行时依赖。
- 如遇异常，请先检查上传包编码是否为 UTF-8 无 BOM。
