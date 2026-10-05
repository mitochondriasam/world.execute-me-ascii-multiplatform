# Windows 源码适配实施记录

本记录对应 mpv 阶段。用户随后要求无需 mpv，Windows 默认后端已改为原生媒体 API；最新结果见 [Windows 原生音频记录](2026-10-04-NATIVE-AUDIO.md)。

日期：2026-10-04（Asia/Singapore）。解释器：uv 管理的 Python 3.12.13。
代码起点：`main` / `9d8e815281a104ccb648ec2f2df88cd9f0cb8c12`，改动保存在工作区，未提交或发布。

## 已实现

- `player.py` 的渲染/CLI 不再依赖 POSIX 导入；资源和输出显式使用 UTF-8。
- `audio_backends` 提供统一状态、播放、暂停、seek、音量、健康查询与关闭；macOS 保留 AVFoundation，Windows/Linux 使用外部 mpv。
- Windows IPC 使用标准库 ctypes、overlapped named pipe、请求 ID 与独立事件处理；读写可超时，取消后可继续通信。连接后才加载媒体，避免丢失启动/解码错误。
- 自然结束使用显式 EOF，暂停健康检查使用有效 IPC 响应。seek 等待 `playback-restart` 与 seeking 结束；已确认的暂停 seek 固定显示目标，恢复播放后回到后端位置。
- 实测发现 null 音频驱动在暂停 seek 后可能报告约 0.2 秒旧缓冲偏移。报告独立记录 `backend_position`，不会把这个差值隐藏为“实测同步误差为零”。
- `terminal_backends` 分离 Windows 和 POSIX 模式/输入；Windows 使用 msvcrt 与 Win32 控制台模式，保留全部控制键；窗口缩放时重新查询尺寸。
- 从初始化开始管理资源；音频启动、通信、终端失败和报告错误均有清理路径，重复关闭可用，主要错误不被音频清理错误掩盖。
- `--mpv` / `MPV_PATH` 和 winget 默认路径发现、`--headless`、测试用空音频输出、扩展播放报告、`run.cmd` 已添加。
- macOS Swift helper 增加明确结束/解码错误状态与 JSON 编码；源码变新时 `run.sh` 自动重建；构建资源清单包含新增 Python 模块。

## 自动检查结果与证据

| 检查 | 结果 | 范围 |
| --- | --- | --- |
| 测试发现 | 25 项：22 通过，3 明确跳过 | [测试记录](2026-10-04-tests.json)，跳过的是尚未构建的 macOS bundle 测试 |
| 快照 | 四个关键中英字幕、默认 GBK/UTF-8 启动、场景边界、小窗口、宽字符与中文/空格源码路径通过 | 不包含字体下的实际显示验收 |
| 真实 mpv | 播放、暂停超过两秒、前后 seek、音量、EOF、重播、崩溃、错误媒体、线程启动失败、回收及原生读取超时/取消通过 | 自生成短 WAV，使用 null 输出 |
| 终端/生命周期 | 全部键位映射、扩展键跨轮读取、部分模式初始化失败、输出失败后的恢复、初始化失败与主要错误保留通过 | 模式变更的失败测试使用替身；本通道非交互控制台 |
| 原曲完整时间线 | FLAC 约 211.91 秒完整播放并渲染，自然结束、报告无错误 | [全曲报告](2026-10-04-full-song-headless.json)，headless/null，不含声音和实际屏幕 |
| 原曲四个时间点 | seek 后暂停稳定，恢复播放后后端位置正确，对应英文字幕存在，近曲尾自然结束，子进程回收 | [FLAC 控制报告](2026-10-04-flac-controls.json)，恢复耗时仅为本次原型测量 |
| 系统音频 | WASAPI 初始化成功，位置推进，输出为 48 kHz 双声道 float，退出后回收 | [系统音频报告](2026-10-04-system-audio.json)，只做一秒输出检查，未由人确认听感 |

全曲报告的帧耗时只反映渲染开销；后端时间或 seek 反馈不直接证明声音与画面无偏差。原曲未转换、改名或移动，仍使用 `C:/Users/mitoc/song.mp3`（实际内容为 FLAC）。

## 当前机器的桌面验收入口

在仓库目录的真正 Windows Terminal 中运行，建议至少 128×45，先用待播放界面确认显示，再按空格开始：

```powershell
.\run.cmd --audio "$env:USERPROFILE\song.mp3" --report windows-playback-report.json
```

若 uv 全局缓存权限受限，等价命令为：

```powershell
uv --no-cache run --locked python -B player.py --audio "$env:USERPROFILE\song.mp3" --report windows-playback-report.json
```

需要人工确认：

- [ ] 原曲声音可听见，全曲前中后字幕/动画同步，无持续累积偏差。
- [ ] 空格/回车、左右、R、Q/ESC、H、1–5、`[`/`]`、`,`/`.`、`+`/`-` 全部正常。
- [ ] 中文和特殊符号、颜色、窗口缩放、小窗口提示、自动换行无显示问题。
- [ ] 正常退出和 Ctrl+C 后光标可见，控制台模式正常，无本次播放残留进程。
- [ ] 后端失败或终端关闭时行为符合预期；系统强杀另行记录限制。

## 后续未完成项

Windows 桌面验收；macOS Swift 编译与实际音频/终端回归；Linux 原生运行回归；按实际音频路径生成 FLAC bundle manifest；Windows 发布包、临时目录包测试与三平台 CI。现有 macOS 包入口和 MP3 构建约定继续保留，源码适配没有将它们伪装成 Windows 发布支持。
