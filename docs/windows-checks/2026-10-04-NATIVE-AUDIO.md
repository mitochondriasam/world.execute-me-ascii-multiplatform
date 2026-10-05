# Windows 原生音频实施记录

2026-10-04，Python 3.12.13，当前 Windows 主机。用户要求“执行不依赖 mpv 的方法”。

Windows 默认后端已改为 `windows-native`。Python 标准库 ctypes 调用系统 DLL：Media Foundation Source Reader 解码、Media Engine 音频模式播放。没有启动播放器/解码器子进程，没有新增 Python 依赖。macOS 默认 AVFoundation、其他平台默认 mpv 保持现有行为；Windows mpv 仍可通过 `--backend mpv` 显式选择。

Media Engine 提供实际媒体时间、暂停、跳转、音量和结束状态。Python 单调时钟只用于刷新调度、超时和测量，字幕与频谱读取媒体时间。COM 初始化、使用与关闭限定同一线程；异步原生回调仅收集事件，避免在回调中重入引擎。

## FLAC 曲尾问题与修正

本机系统 FLAC source 将 211.906666667 秒原曲的 duration 返回为 211.0 秒，直接跳转到 211.8 秒被截至 210.995 秒；改为 `.flac` 后缀也一样。

因此 FLAC 先由系统解码器输出整数 PCM 到独立临时目录，再交给原生 Media Engine。你的原曲解码为 9,345,084 帧、44,100 Hz、16-bit 双声道，样本数与 FLAC STREAMINFO 精确匹配，约 35.7 MiB 临时空间；两次初始化实测约 0.28–0.45 秒。解码过程核对输出位深不低于原始 FLAC，未验证其他位深或多声道文件。正常退出及初始化失败清理临时文件；操作系统强杀可能留下临时文件。

原曲路径 `C:/Users/mitoc/song.mp3` 未改名、移动或写入。前后 SHA-256 相同：`d7bbcac06aa5f688ef77205fa47dd054a836ed3550dc4dd3117e69b5e317f63d`。

## 验证证据

- [原曲控制报告](2026-10-04-native-controls.json)：阻止 subprocess.Popen，原生解码并播放；67.3、124.2、159.85、183.2、211.8 秒暂停跳转正确，seek 反馈约 0–16 ms；曲尾结束、重播和临时文件回收通过。volume=0，使用真实系统音频设备。
- [全曲报告](2026-10-04-native-full-song.json)：完整约 211.91 秒自然结束，headless 渲染 5,090 帧；volume=0，禁止启动外部进程，报告无错误，临时文件清理成功，原曲哈希未变。
- [测试报告](2026-10-04-native-tests.json)：33 项，30 通过、3 跳过。覆盖源码、mpv 可选后端、原生控制、错误媒体、部分初始化失败、解码临时目录回收、跨线程保护、终端与生命周期；跳过的是缺少构建的 macOS 包测试。

原生接口依据微软 [IMFMediaEngine](https://learn.microsoft.com/en-us/windows/win32/api/mfmediaengine/nn-mfmediaengine-imfmediaengine) 和 [Source Reader](https://learn.microsoft.com/en-us/windows/win32/medfound/source-reader)，COM ABI 对照 [Windows SDK 头文件](https://github.com/microsoft/win32metadata/blob/main/generation/WinSDK/RecompiledIdlHeaders/um/mfmediaengine.h)。

## 使用与未完成验收

在本机 Windows Terminal、仓库目录中运行：

```powershell
.\run.cmd
```

默认读取项目内 `input/song.mp4`，与调用时工作目录无关。本轮未放入媒体，当前启动会提示缺失路径；放入文件后按空格开始。原曲验证记录仍对应此前通过 `--audio` 指定的 `~/song.mp3`，尚未验证实际 MP4 文件。可加 `--autoplay` 或显式 `--backend windows-native`。`--headless` 只关闭画面输出，仍用系统音频设备；原生后端不支持 null 输出。

仍需人工确认全曲听感/声画同步、真实终端显示、键盘与缩放、Ctrl+C 后终端模式恢复。自动静音检查不能替代这些验收。本轮未制作 Windows 发布包，未运行 macOS/Linux 原生回归。

2026-10-05 PR 复测发现 Media Engine 的 Pause 返回后，媒体时钟还会推进约 35 ms。共享暂停方法现等待媒体位置连续稳定 50 ms（受现有超时限制），避免返回尚未冻结的时间。正常 Windows 权限下复跑 33 项测试：30 通过、3 项 macOS 包测试跳过；受限沙箱不能替代音频设备/IPC 的正常权限检查。
