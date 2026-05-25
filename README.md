# astrbot_plugin_meme_stickers

本插件由 [lgc-NB2Dev/nonebot-plugin-meme-stickers](https://github.com/lgc-NB2Dev/nonebot-plugin-meme-stickers) 迁移而来，面向 AstrBot 运行环境重构。

## 插件信息

- 插件名：`astrbot_plugin_meme_stickers`
- AstrBot 显示名：`Arc/pjsk表情包制作`
- GitHub 仓库：[`kyuphoenix/astrbot_plugin_meme_stickers`](https://github.com/kyuphoenix/astrbot_plugin_meme_stickers)
- 主要能力：
  - 查看本地与在线贴纸包列表
  - 在线安装、更新、启用、禁用、删除贴纸包
  - 交互式制作 pjsk / arcaea 贴纸
  - 直接按指定贴纸生成表情包

<details>
<summary><strong>安装失败必看！！！</strong></summary>

### 安装后提示 `libEGL.so.1` 缺失？

由于本插件基于 `Skia` 图形引擎开发，在 Docker 镜像或者部分系统中运行时，可能会因为缺少底层图形依赖而报错：

> `AssertionError: libEGL.so.1: cannot open shared object file: No such file or directory`

无需重建容器，只需两步即可手动补全依赖。

### 1. 进入 AstrBot 容器

宿主机直接运行 AstrBot 可跳过这一步。

```bash
docker exec -it -u root astrbot /bin/bash
```

### 2. 安装依赖

```bash
apt-get update && apt-get install -y libegl1 libgl1 libglib2.0-0t64 libfontconfig1 libpng-dev libjpeg-dev fontconfig && fc-cache -fv
```

该命令适用于 `docker` 容器或 `debian/ubuntu` 系统。若宿主机是其他系统，需要自行补全 `libEGL.so.1` 相关依赖。

</details>

## 命令说明

### 主命令

- `/meme-stickers help`
  - 显示插件帮助信息。
- `/meme-stickers list`
  - 查看当前可用的本地贴纸包列表。
- `/meme-stickers list all`
  - 查看所有本地贴纸包，包括不可用贴纸包。
- `/meme-stickers list online`
  - 查看在线 Hub 中可下载的贴纸包列表。
- `/meme-stickers install <slug...>`
  - 安装指定贴纸包，例如 `/meme-stickers install pjsk arcaea`。
- `/meme-stickers install all`
  - 安装 Hub 中当前全部贴纸包，并自动补全共享字体资源。
- `/meme-stickers update`
  - 更新所有已安装贴纸包。
- `/meme-stickers reload`
  - 重载本地贴纸包索引与共享字体。
- `/meme-stickers generate`
  - 进入“先选贴纸包，再选分类，再选贴纸”的交互式生成流程。
- `/meme-stickers generate <pack_slug> <贴纸名> <文本>`
  - 直接按指定贴纸生成图片。
- `/meme-stickers delete <pack...>`
  - 删除指定贴纸包。
- `/meme-stickers enable <pack...>`
  - 启用指定贴纸包。
- `/meme-stickers disable <pack...>`
  - 禁用指定贴纸包。
- `/meme-stickers debug-font <文本>`
  - 使用固定贴纸测试当前字体渲染，并返回字体调试信息。
- `/meme-stickers fetch-emoji-font`
  - 手动下载或补全 Emoji 字体资源。

### 快捷制作命令

- `/pjsk`
  - 直接进入 `pjsk` 贴纸包的交互式制作流程。
- `/arc`
  - 直接进入 `arcaea` 贴纸包的交互式制作流程。
- `/arcaea`
  - `arc` 的别名，效果相同。

## 交互说明

- 输入 `r`、`b`、`back`、`return`
  - 返回上一步。
- 输入 `0`、`q`、`quit`、`exit`、`cancel`
  - 退出当前交互。
- 交互采用静默超时
  - 超时后会话自动失效，不额外发送提示。

## 资源与字体

- 贴纸资源目录：`plugin_data/astrbot_plugin_meme_stickers/packs/`
- pjsk 贴纸目录：`plugin_data/astrbot_plugin_meme_stickers/packs/pjsk/`
- arcaea 贴纸目录：`plugin_data/astrbot_plugin_meme_stickers/packs/arcaea/`
- 共享字体目录：`plugin_data/astrbot_plugin_meme_stickers/packs/_shared/`

插件运行时会优先从以上数据目录读取字体与资源，不依赖插件目录内置字体。

## 安装与打包

1. 将 `astrbot_plugin_meme_stickers` 文件夹打包为 zip。
2. zip 顶层必须是插件文件夹本身，不能直接把 `main.py` 放在压缩包根目录。
3. 在 AstrBot 插件管理页面上传该 zip 安装。

## 依赖

依赖文件位于同目录下的 `requirements.txt`，当前包含：

- `skia-python`
- `pydantic>=2`
- `httpx`
- `tenacity`
- `yarl`
- `typing_extensions`
