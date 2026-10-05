# Windows 检查结果与修订执行计划

检查日期：2026-10-03（Asia/Singapore）。
实施更新：2026-10-04。最新结果见 [Windows 原生音频记录](windows-checks/2026-10-04-NATIVE-AUDIO.md)：用户要求无需 mpv 后，Windows 默认已改为 Python ctypes + 系统 Media Foundation / Media Engine。先前 [mpv 实施记录](windows-checks/2026-10-04-IMPLEMENTATION.md) 与下文首次检查表保留为历史基线；桌面视觉/听感验收及发布包仍待完成。
依据：用户提供的 `C:/Users/mitoc/Downloads/WINDOWS_HANDOFF.md`。
代码基线：`main`，`9d8e815281a104ccb648ec2f2df88cd9f0cb8c12`，与交接文档一致。
检查开始时工作区干净；本轮只新增检查记录与修订计划，没有修改播放器、安装依赖、提交或发布。

上述描述对应首次检查。后续用户已同意用 winget 安装 mpv、用 uv 管理项目和采用 Python 3.12；环境准备结果与 FLAC 检查见下方追加记录。2026-10-04 按“开始执行”进入代码实施。

交接文档中的实施建议作为检查依据。最初任务为检查并修正执行计划；后续实施结果和未完成验收分别记录，避免把自动检查当作桌面验收。

## 本轮实际结果

可复查的命令、退出码、traceback、编码与检查范围见 [原始检查记录](windows-checks/2026-10-03-baseline.json)。

| 项目 | 结果 | 对计划的影响 |
| --- | --- | --- |
| 原生 Windows | `sys.platform=win32`，AMD64/X64；OS `10.0.26300`，注册表 build `26300.9550`、DisplayVersion `26H2` | 已完成原生 Windows 基线复现；不使用 WSL 结果替代 |
| 系统产品名称 | 注册表 ProductName 为 `Windows 10 Pro`；CIM 查询 Access denied | 记录实际版本/build，不据此认定已验证 Windows 11；商业版本名称留待本地桌面确认 |
| PowerShell / Git | PowerShell 7.6.5；Git 2.55.0.windows.3 | 可继续本地源码检查 |
| Python | 直接 `python` 为 CPython 3.14.7 64 bit；路径为 `C:/Users/mitoc/AppData/Local/Programs/Python/Python314/python.exe` | 本轮以可用的 3.14.7 检查；保留 3.12 兼容目标，不将其标为已验证 |
| Python launcher | `py -0p` 未找到 Python；`py -3.12 --version` 退出 112 | 当前执行会话不能使用交接文档的 `py -3.12` 命令；不能据此断言整机绝无其他 Python |
| `--help` | 退出 1：`player.py:5` 顶层导入 `termios` 失败 | P0 已真机复现 |
| 四个关键快照 | 67.3、124.2、159.85、183.2 秒均退出 1，错误同上 | 字幕、画面、尺寸尚未验收；`-X utf8` 无法解决平台导入 |
| 任意工作目录 | 从临时目录以绝对路径调用上述快照，也在导入处失败 | 已尝试命令；资源定位与成功渲染仍待验证 |
| 默认资源编码 | `utf8_mode=0`，locale 为 cp936；默认读取 `lyrics.json` 实际抛出 GBK `UnicodeDecodeError` | 修复导入后还会遇到独立编码阻塞，必须同轮修复 |
| 显式 UTF-8 资源读取 | 三份 JSON 均成功读取、解析 | 资源本身有效，不应通过转存为 GBK 解决 |
| 重定向编码 | Python 管道 stdin/stdout/stderr 为 GBK；PowerShell OutputEncoding 为 UTF-8 | 父 shell 的 UTF-8 设置不足以保证 Python 的输出编码 |
| 渲染字符 | 静态检查发现 `scenes.py` 的 `░`、`▒`、`♥` 等字符无法编码为 GBK | 输出测试必须覆盖场景符号及中文，不能只断言英文字幕；尚未成功输出实际帧 |
| 终端 | `TERM=dumb`，无 `WT_SESSION`；stdin/stdout 非 TTY，Win32 `GetConsoleMode` 均失败（error 6） | 本通道不能验收按键、VT、窗口缩放、光标或终端模式恢复 |
| Windows Terminal | `wt.exe` 可解析到 WindowsApps 中的 0 字节应用执行别名 | 不等于已确认安装版本或当前运行于 Windows Terminal |
| mpv | PATH 与 App Paths 注册表项未发现可执行文件 | 原型前需安装或显式指定实际路径；不声称整机任何位置均无 mpv |
| 音频 / helper / 发布包 | `media/song.mp3`、`audio-clock`、`dist/world-execute-mv.pyz` 均不存在 | 原曲同步、现有 helper 播放和 bundle 测试均无本轮运行条件 |
| 声卡 | Win32_SoundDevice CIM 查询 Access denied | 未确认真实可用输出设备，不把权限失败归因为没有声卡 |
| Python 语法 | 五个 `.py` 文件通过 `compile()` 检查，不导入执行、不生成 pyc | 只代表语法通过，不代表源码运行通过 |
| 默认 unittest 发现 | `python -B -m unittest discover -v`：Ran 0 tests，退出 5 | 后续 CI 必须显式指定测试目录并检查执行数量 |
| 显式测试目录发现 | `TestLoader().discover('tests')` 找到三个 bundle 测试；未执行 | 现有测试均依赖缺失的包；需要增加独立源码测试 |

Linux、macOS 回归、本地桌面播放、中文/空格目录成功渲染以及发布包验收，本轮均未完成。交接文档中的 Linux 历史结果不能记为本轮通过。

## 按用户意见完成的环境准备与 FLAC 检查

- winget 实际可用版本为 `1.29.380`。沙箱内不能直接运行应用别名，允许访问本机安装环境后查询成功。包 `shinchiro.mpv` 无适用的 user-scope 安装器，按默认范围安装成功，安装器哈希校验通过。
- winget 包版本为 `0.41.0`，实际二进制版本为 `v0.41.0-244-gaf9c81fa1`。安装目录 `C:/Program Files/MPV Player/`；命令行验证使用 `mpv.com`。当前进程 PATH 尚未刷新，后续发现逻辑应支持配置绝对路径，不能只查 PATH。
- 已有 uv `0.11.15` 和 uv 管理的 Python `3.12.13`。已创建 `pyproject.toml`、`.python-version`、`uv.lock` 及被忽略的 `.venv/`；`package=false`，无第三方 Python 依赖。`uv sync` 与锁定运行的 Python 版本检查通过。
- 当前沙箱访问 uv 全局缓存会被拒绝，本轮用 `uv --no-cache ...` 完成初始化/同步/运行；普通桌面可以使用常规 `uv sync --locked`，需要隔离缓存时可加 `--cache-dir .uv-cache`。
- Python 3.12.13 下 `player.py --help` 同样失败于 `termios`；换解释器不消除跨平台代码阻塞。默认 locale 仍为 cp936，编码修复仍必须执行。
- 用户提供原曲 `~/song.mp3`（`C:/Users/mitoc/song.mp3`）。文件头为 `fLaC`，实际为原生 FLAC；44,100 Hz、双声道、16 bit、9,345,084 个采样，大小 25,973,704 字节。
- FLAC STREAMINFO 时长为 `211.90666666666667` 秒，与配置 `211.906667` 秒仅相差约 0.33 微秒。现有频谱为 30 fps、6,358 帧，覆盖约 211.9333 秒；它与歌曲时长的约 26.7 ms 差值来自帧数覆盖边界，不作为需要拉伸歌曲的证据。
- 安装后的 mpv 按内容识别该 `.mp3` 文件为 FLAC，前 0.2 秒以 `--ao=null` 解码成功；标签显示 Mili / Miracle Milk / world.execute (me) ;。文件另有 800×800 MJPEG 封面图，原型启动须禁用视频/音频封面显示。
- 以上支持“文件可解码、时长匹配”的判断，尚不证明整曲无损坏、与原时间线为相同剪辑或真实声画同步。未更名、移动、转换或复制用户的原曲。

详细证据：[依赖与解码检查](windows-checks/2026-10-03-dependencies.json)、[FLAC 元数据](windows-checks/2026-10-03-flac-metadata.json)。首次检查记录保留原样，避免覆盖当时的环境结果。

FLAC 接入修正：

1. 首次 Windows 播放使用 `--audio` 指向用户原文件，无需转为 MP3。建议后续本地工作副本命名 `media/song.flac`，但不将 FLAC 仅改名为 MP3 作为正式格式约定。
2. 原型使用 `--no-video --no-audio-display` 避免内嵌封面打开窗口；按用户配置、实际后端验证音频路径和解码器，不仅按扩展名判断格式。
3. 核对前中后至少三个歌曲时间点；若只是字幕偏移可用现有 `--offset`，若整段音频起点不同则同时修正动画/字幕/频谱的统一时间映射。逐渐增加的偏差或不同剪辑不能只靠固定 offset 处理。
4. FLAC 大小约 26 MB，分发时评估临时解包和包体积；按实际 `config.audio` 建立构建资源清单与测试断言，移除 `tools/build_bundle.py`、`tests/test_bundle.py` 的固定 MP3 假设。
5. macOS AVFoundation 对此原曲的解码与控制仍需真机验证，不根据 Windows mpv 结果推断它通过。保留现有 macOS MP3 发布流程，直到音频输入泛化经过回归。

## 相对原交接方案的修正

1. 增加“阶段 0：执行环境与依赖确认”。使用 uv 与 `.python-version` 的 Python 3.12；环境已准备。按用户最新要求，Windows 默认使用系统 Media Foundation，mpv 不再是前置依赖。
2. 第一阶段同时修复 POSIX 顶层导入、UTF-8 资源读取和输出。保留不带 `-X utf8` 的测试，不能用环境开关掩盖实际默认 GBK 路径。
3. 音频原型与终端原型各自验证后接入实时循环。Windows 原生后端和源码快照均无需 mpv。
4. 将资源生命周期修复提前到接口建立阶段；分别保证进程、通信句柄、终端、信号和报告写入的清理，避免某个清理失败阻止其余清理。
5. 测试入口显式使用 `-s tests`，区分源码、Windows 原生、可选 mpv 集成与 bundle 测试；记录执行数量与跳过理由。
6. 交付拆为自动检查与本地桌面验收里程碑。后者需要原曲、系统媒体组件、可用声卡与交互终端；未完成时保留“待验收”。

## 修订后的执行顺序

### 阶段 0：确认可执行环境（部分完成）

- 已完成 SHA、工作区、可运行 Python、默认编码、导入失败与依赖路径检查。
- 后续命令默认使用 `uv run --locked python`（3.12）或项目 `.venv/Scripts/python.exe`。本轮确认的 3.14 结果仅保留为初始基线，不再作为主要开发环境。
- 在本地桌面确认 Windows 产品名称、Windows Terminal 实际版本、默认字体和音频输出设备。CIM 读取限制不影响先做源码适配。
- mpv 路径和 `--version` 已确认，实施时仍需提供命令行或配置中的路径覆盖，适配有空格/中文的路径。依赖查找失败应给出具体提示；winget 管理外部二进制，uv 不负责安装 mpv。
- 原曲 FLAC 已定位且时长匹配；后续核对真实歌曲时间点和声画同步。自生成短 WAV 用于故障/控制测试，不能替代原曲验收。

阶段门槛：源码开发已有可用解释器；Windows 原生音频需要系统媒体组件和测试音频；全曲桌面验收需要原曲、真实输出设备及交互终端。

### 阶段 1：Windows 源码快照与编码

主要文件：`player.py`，新增独立源码回归测试。优先保持 `scenes.py` 的动画逻辑不变。

1. 将 `termios`、`tty` 以及 POSIX 专属终端代码置于平台实现或实时路径；`--help`、导入渲染模块、快照均无需加载音频和终端后端。
2. `Film` 三份 JSON 明确用 UTF-8 读取；报告和新增文本资源同样指定编码。子进程文本协议分别明确编码，不依赖本机代码页。
3. 为快照控制台与管道输出确定 UTF-8 策略；保留 Unicode 字符，不以忽略/替换乱码作为成功条件。测试子进程捕获原始 bytes 并严格 UTF-8 解码，避免 PowerShell 二次转码掩盖错误。
4. 新增 `tests/test_source.py`：四个关键英文及对应中文字幕、无 ANSI 的 plain 输出、所有七个场景、64×24 与低于最低尺寸的提示、宽字符边界、任意工作目录、中文/空格源码路径。
5. 同时执行默认启动与 `-X utf8` 启动。先在 uv 的 Python 3.12.13 上通过，随后在 Linux 及其他目标解释器上复测；不能只模拟缺失模块便宣称跨平台通过。

完成门槛：`--help` 与上述源码测试实际通过；不需要 mpv、歌曲或已构建发布包。字体下的视觉宽度仍留给桌面验收。

### 阶段 2：音频和终端接口、资源生命周期

可采用交接文档的 `audio_backends/` 与 `terminal_backends/` 划分；不强制仅为文件拆分而抽出全部渲染逻辑。

- 音频统一提供播放、暂停、绝对 seek、音量、位置/时长、暂停/缓冲/结束、错误、有效状态更新时间与关闭。播放器不访问 `proc`、socket 或 named pipe。
- 区分“位置最近更新”与“IPC 最近有效响应”。暂停和媒体空闲时位置事件稀少不能触发当前固定两秒时钟停更错误。
- 终端统一进入、恢复、尺寸查询、绘制和按键事件；保留全部现有控制语义。
- 从第一次资源获取起建立清理边界，覆盖音频启动成功但终端初始化失败、部分信号注册失败和报告写入失败。
- 音频关闭应可重复调用；退出→限时等待→必要时终止/杀死→再次等待回收，关闭通信句柄、处理读取线程。每项资源独立尝试清理。
- 只注册平台存在且适用的信号，并恢复已成功注册的处理器。Ctrl+C、缺依赖等错误使用适合当前平台的中文提示。
- 先用可控替身验证控制语义、EOF 与崩溃的区别、超时及初始化失败的清理；替身结果不能替代真实 Windows 后端验收。
- 同步更新未来构建资源清单；保留 macOS AVFoundation 后端，并将其真机播放回归标为待验证。

完成门槛：接口契约及故障清理测试通过，不再由上层推测“playing=False 且位置回零”等于自然结束。

### 阶段 3A：Windows 原生音频（自动检查完成）

`audio_backends/windows_native.py` 使用 Python ctypes 调用系统 Media Engine；FLAC 通过系统 Source Reader 解码成临时 PCM，避免时长取整及曲尾跳转截断。已完成播放、长暂停、前后跳转、音量、自然结束、重播、初始化失败和临时资源清理检查；原曲全曲静音 headless 渲染通过，30 项测试通过、3 项 macOS 包测试跳过。证据见 [原生记录](windows-checks/2026-10-04-NATIVE-AUDIO.md)。

桌面声音与同步验收仍需阶段 4；Windows 默认不会启动外部播放器。以下 mpv 内容保留为可选后端的实现与回归规范。

#### 可选 mpv 后端（此前已完成）

实施时参考 [mpv 官方手册的 JSON IPC 章节](https://mpv.io/manual/stable/#json-ipc)，并以安装版本的实际行为为准。Windows named pipe 原型已实现并运行真实 mpv 控制测试，下列规范继续作为后续平台验收依据。

- Windows named pipe 通信先做最小原型，再决定标准库/Win32 API 或额外依赖；不要直接复用 Unix socket。
- 每次启动使用独立 IPC 名称；请求响应按 request_id 匹配，事件独立处理；管道读取、连接重试、超时、断连与关闭须能退出，不能永远阻塞读取线程。
- 隔离用户 mpv 配置、脚本、终端键盘输入及视频窗口，避免污染 MV 终端。启动参数以实际版本验证，不在计划中视为已兼容。
- 等媒体加载、有效时长和可用位置后才 ready；使用后端位置驱动画面，monotonic 只负责调度与超时。
- 显式设置初始音量为现有播放器语义的 75%，seek/重播/章节跳转使用绝对目标；暂停、seek、缓冲、结束时重置任何插值。
- 明确自然结束与进程崩溃的区别，确定 EOF 后仍可重播的进程策略。验证暂停/空闲时的请求健康检查及无音频输出设备的错误。
- 自生成短音频覆盖加载、位置推进、暂停保持、seek 回报、音量、结束、重播、错误文件、中文路径、断连和进程清理。随后使用原曲验证全曲同步。

完成门槛：真实 Windows mpv 的自动集成测试通过；真实声音输出与全曲同步仍需阶段 4。

### 阶段 3B：Windows 终端原型

- 可先评估 `msvcrt` 按键读取及 Win32 控制台模式；方向键扩展序列统一映射为事件，保留 SPACE/ENTER、左右、R、Q/ESC、H、1–5、`[`/`]`、`,`/`.`、`+`/`-`。
- 保存输入/输出原始模式，启用所需 VT；退出恢复准确的原始状态。失败时恢复已修改的部分，不打开 `/dev/tty`。
- 明确实时播放对交互句柄的要求和重定向行为；快照应支持管道。本轮 GetConsoleMode 失败不等于 Windows Terminal 不支持 VT。
- 先验证模式进入/恢复与事件解析，再在真正 Windows Terminal 中验证 ANSI/256 色、备用屏幕、中文/特殊符号、窗口缩放与自动换行。

完成门槛：本地桌面终端原型的实际结果已记录；后台管道测试不用于判定视觉或真实键盘输入通过。

### 阶段 4：接入源码完整播放并做桌面验收

原型分别通过后接入播放器循环，使用原曲在本地 Windows Terminal 播放全曲。

- 验证全部键位、初始待播放状态、暂停时间稳定、前后 seek、章节跳转、重播、音量、自然结束。
- 验证窗口缩放、小窗口提示、字体下中英文宽度和符号显示。
- 分别验证正常退出、Ctrl+C、后端崩溃、初始化中途失败和终端关闭；记录可恢复退出的模式恢复及本次创建的残留进程。系统强杀的限制单独说明。
- 报告加入后端有效状态/通信时间、seek 请求目标与反馈时间；不把帧渲染耗时解释为声画误差。
- seek 后约 300ms 内恢复作为暂定原型目标，实测后给出阈值；记录全曲前中后可听见的同步点与显示偏差，不能仅依靠后端时间报告宣称无漂移。

完成门槛：自动测试和本地桌面验收两组结果齐全；失败、跳过、待验证逐项说明。缺原曲时只交付源码与后端控制里程碑，不标记全曲验收完成。

### 阶段 5：Windows 启动与分发（后续）

源码启动器 `run.cmd` 已完成，支持路径引用、参数透传及任意工作目录。Windows 默认依赖为 Python 3.12 + 系统 Media Foundation，无外部音频工具；mpv 仅作为显式可选后端。不将免安装 exe 作为前置条件。

构建与 manifest 参数化平台/架构/后端，保留资源 SHA-256 和路径校验。新增包内模块时同时更新清单。Windows 临时目录测试显式设置 TEMP/TMP，等待音频进程回收与句柄关闭后再清理；保留 macOS TMPDIR 行为。

Windows、Linux、macOS CI 分别运行源码测试；mpv 集成和 bundle 测试采用有实际依赖的独立任务。缺依赖必须展示明确跳过原因或预检失败，不得全组跳过后仍标记平台验收通过。

## 后续实施时的命令入口

下面的快照命令现已通过 Windows 源码测试。项目使用 uv 的 Python 3.12，无需依赖 launcher。当前沙箱需要隔离全局缓存，因此示例加 `--no-cache`；普通本地桌面可省略。

```powershell
uv --no-cache sync --locked
uv --no-cache run --locked python --version
uv --no-cache run --locked python -B player.py --help
uv --no-cache run --locked python -B player.py --snapshot 159.85 --plain --width 125 --height 45
uv --no-cache run --locked python -X utf8 -B player.py --snapshot 159.85 --plain --width 125 --height 45
```

已实现的阶段 1 源码测试入口：

```powershell
uv --no-cache run --locked python -B -m unittest discover -s tests -p 'test_source*.py' -v
```

阶段 2、3 新增契约/集成测试后，使用各组明确的文件模式或模块名运行并核对执行数量。完整测试入口为 `unittest discover -s tests -v`；只有准备好其依赖后才运行，当前三个 bundle 测试仍要求真实构建包。

阶段 4 桌面验收：按最新默认入口，将媒体放入项目 `input/song.mp4` 后，在真正 Windows Terminal 中执行。本轮未放入该文件：

```powershell
.\run.cmd
```

Windows 默认使用 `windows-native`，无需 mpv。`--backend mpv` 是显式可选入口，支持 `--mpv` / `MPV_PATH`。`run.cmd` 可透传参数并从任意工作目录调用。

## 当前交付和下一步

已完成：基线与环境准备；UTF-8 和 Windows 快照修复；音频/终端接口与清理；Windows 默认原生媒体后端及可选 mpv 后端；按键映射和原生控制台模式保存/恢复；源码启动器；原曲全曲原生媒体时间线/静音渲染、精确 FLAC 样本数和曲尾 seek 检查。证据范围见最新原生实施记录。

下一轮在真实 Windows Terminal 中完成阶段 3B/4 的显示、键盘、缩放、Ctrl+C 和听感/声画同步验收，然后推进阶段 5 的平台化打包、FLAC manifest、包测试与三平台 CI。macOS Swift helper 已更新明确 ended 协议，构建清单已包含新增模块；因无 macOS/Linux 执行环境，其实际回归仍待验证。
