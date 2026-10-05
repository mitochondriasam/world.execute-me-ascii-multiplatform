"""Audio implementations are imported only for real playback."""
from dataclasses import dataclass
from pathlib import Path
import sys


@dataclass
class AudioState:
    position: float = 0.0
    backend_position: float = 0.0
    duration: float = 0.0
    paused: bool = True
    buffering: bool = False
    seeking: bool = False
    ended: bool = False
    volume: float = 0.75
    updated_at: float = 0.0
    connected_at: float = 0.0


def create_audio(path, *, backend='auto', mpv=None, output='auto'):
    selected = ({'darwin': 'avfoundation', 'win32': 'windows-native'}.get(sys.platform, 'mpv')
                if backend == 'auto' else backend)
    if selected == 'windows-native':
        from .windows_native import WindowsNativeAudio
        return WindowsNativeAudio(Path(path), output=output)
    if selected == 'avfoundation':
        if output == 'null':
            raise RuntimeError('空音频输出需使用 --backend mpv；AVFoundation 使用真实声音输出。')
        if sys.platform != 'darwin':
            raise RuntimeError('AVFoundation 后端仅支持 macOS；Windows 请使用 windows-native。')
        from .avfoundation import AVFoundationAudio
        return AVFoundationAudio(Path(path))
    if selected != 'mpv':
        raise ValueError(f'未知音频后端：{selected}')
    from .mpv import MpvAudio
    return MpvAudio(Path(path), executable=mpv, output=output)
