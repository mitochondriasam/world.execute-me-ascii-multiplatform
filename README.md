# world.execute(me); —ascii

![world.execute(me);](docs/images/mv-cover.png)

Mili《world.execute(me);》的字符动画。支持中英字幕、原曲同步播放和终端字符动画。

## 单文件运行（推荐）

从本仓库的 **Releases** 下载 `world-execute-mv-macos.zip` 并解压。音乐、动画、字幕、频谱数据和音频播放组件已经内嵌在 `world-execute-mv.pyz` 内，无需另外下载或指定 MP3。

需要 **macOS 12 或更新版本、Python 3.9 或更新版本**。音频组件同时包含 Apple Silicon 和 Intel 架构。终端播放器自身只使用 Python 标准库。

在 macOS「终端」中进入解压目录运行：

```sh
python3 world-execute-mv.pyz
```

也可双击 `运行单文件.command`，在系统终端中播放。按空格开始。推荐全屏，终端至少 64 列 × 24 行，128 列 × 44 行及以上效果更好。

```sh
# 从 2:38.7 开始直接播放
python3 world-execute-mv.pyz --start 158.7 --autoplay
```

内嵌音乐是随程序封装的资源，不是加密或 DRM。播放时会解包到当前用户的临时目录，正常退出后清理；不会读取旧电脑 Downloads 中的文件。运行过程无需联网。

## 操作

| 按键 | 功能 |
| --- | --- |
| 空格 | 开始／暂停 |
| 左／右 | 后退／前进 5 秒 |
| R | 从头播放 |
| Q | 退出 |
| H | 显示全部帮助 |
| 1–5 | 跳转章节 |

## 从源码运行

仓库不保存媒体文件。默认读取项目目录中的 `input/song.mp4`；放入该文件后，可直接运行 `run.cmd`，无需参数。路径相对于项目目录解析，与启动时的工作目录无关。当前只保留空的 `input/` 目录；缺少媒体时会提示完整路径。使用 Release 播放包无需另外放入媒体。

开发环境使用 uv 管理，默认 Python 3.12：

```powershell
uv python install 3.12
uv sync --locked
uv run --locked python --version
uv run --locked python -B player.py --help
```

项目目前仅依赖 Python 标准库。`uv.lock` 和 `.python-version` 保存开发环境配置。Windows 默认通过 `ctypes` 调用系统 Media Foundation / Media Engine，无需 mpv、FFmpeg 或第三方 Python 包；终端使用原生控制台。实际显示和声画同步验收状态见 [Windows 执行计划](docs/WINDOWS_EXECUTION_PLAN.md)。

音频文件应保留实际格式后缀。Windows 原生后端按文件头识别 FLAC，包括误命名为 `.mp3` 的文件。为解决系统 FLAC 时长取整和曲尾跳转截断，先用系统 Source Reader 解码到临时 PCM WAV，再由 Media Engine 播放；退出或初始化失败会清理临时文件。原曲的 44.1 kHz / 16-bit 双声道 PCM 已验证精确样本数，约占 35.7 MiB 临时空间；原文件不改动。MP4 等其他媒体直接由系统引擎以音频模式打开。macOS 构建资源清单读取 `config.json` 的媒体路径。

### Windows 源码播放

在 Windows Terminal 中运行，建议窗口至少 128 列 × 45 行：

```powershell
.\run.cmd
# 等价源码命令，默认使用 input/song.mp4
uv run --locked python -B player.py
# 指定其他媒体时仍可覆盖默认路径
.\run.cmd --audio "C:\path\to\song.flac"
```

按空格开始；也可添加 `--autoplay`。Windows 默认选择 `windows-native`，通过系统媒体引擎实现播放、暂停、跳转和音量，并读取媒体时间驱动字幕/频谱。需要本机 Windows Media Foundation 和音频输出设备；缺失组件或设备错误会明确报错。

已有 mpv 可作为显式可选后端：`--backend mpv`。此时可用 `--mpv "C:\Program Files\MPV Player\mpv.exe"` 或 `MPV_PATH` 指定路径；默认发现包含 winget 安装目录。原生后端不会自动启动 mpv。

快照和自动测试不需要交互控制台：

```powershell
uv run --locked python -B player.py --snapshot 159.85 --plain
uv run --locked python -X utf8 -B -m unittest discover -s tests -v
# 空音频输出检查时间线和渲染，不验证真实声音或终端显示
uv run --locked python -B player.py --headless --backend mpv --audio-output null --audio "C:\path\to\song.flac" --autoplay --report playback-report.json
```

原生后端的 `--headless` 只关闭屏幕输出，仍使用系统音频设备；`--audio-output null` 需要显式选择 mpv。缺少已构建 macOS 包时，其三个 bundle 测试会明确跳过；mpv 测试在缺少播放器时跳过，Windows 原生测试使用静音 PCM。Windows 发布包和免依赖 exe 尚未提供。

### macOS 源码播放

首次构建音频组件需要 Apple Command Line Tools（含 Swift 编译器）：

```sh
xcode-select --install
```

然后执行：

```sh
./run.sh
```

启动脚本在缺少 `audio-clock` 或 Swift 源码更新时自动编译本机架构。双击 `播放MV.command` 可在 macOS 系统终端中运行源码版。

## 重新打包

```sh
python3 tools/build_bundle.py
python3 tests/test_bundle.py
```

构建输出在 `dist/`：

- `world-execute-mv.pyz`：内嵌音乐的单文件播放器。
- `world-execute-mv-macos.zip`：包含播放器、启动器、说明的分发包。
- `SHA256SUMS.txt`：下载校验值。

音频以 macOS 音频时钟驱动画面；暂停、跳转时字幕与动画跟随音频时间。构建会生成 universal 音频组件，并在单文件包内记录各资源 SHA-256 以检查完整性。

## 收录范围

本仓库为项目归档，包含当前播放器、字幕、频谱和构建工具。音乐仅内嵌于 Release 播放包。

原曲与歌词：Mili《world.execute(me);》。本项目是个人创作与备份，未对原曲、歌词或其他第三方素材授予额外使用许可。
