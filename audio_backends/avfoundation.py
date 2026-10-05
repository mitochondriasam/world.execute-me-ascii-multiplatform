"""The original macOS Swift helper behind the common audio interface."""
from dataclasses import replace
from pathlib import Path
import json
import subprocess
import threading
import time

from . import AudioState


class AVFoundationAudio:
    name = 'avfoundation'

    def __init__(self, path):
        self._state = AudioState()
        self._lock = threading.Lock()
        self._error = ''
        self._closed = False
        self._stderr = []
        self.last_seek_seconds = None
        self.last_seek_target = None
        helper = Path(__file__).resolve().parents[1]/'audio-clock'
        if not helper.is_file():
            raise RuntimeError('找不到 macOS audio-clock；请先运行 ./build-audio.sh。')
        self._proc = subprocess.Popen([str(helper), str(path)], stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      text=True, encoding='utf-8', bufsize=1)
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._error_reader = threading.Thread(target=self._read_errors, daemon=True)
        try:
            self._reader.start()
            self._error_reader.start()
            deadline = time.monotonic()+8
            while not self.poll().duration:
                if time.monotonic() >= deadline:
                    raise RuntimeError('macOS 音频引擎没有响应。')
                time.sleep(.01)
        except BaseException:
            self.close()
            raise

    def _read_errors(self):
        for line in self._proc.stderr:
            self._stderr.append(line.strip())
            self._stderr[:] = self._stderr[-30:]

    def _read(self):
        for line in self._proc.stdout:
            try:
                message = json.loads(line)
                with self._lock:
                    if 'error' in message:
                        self._error = str(message['error'])
                    elif 'ended' not in message:
                        self._error = 'audio-clock 协议过旧，请运行 ./build-audio.sh 重新构建。'
                    else:
                        now = time.monotonic()
                        self._state = AudioState(position=message['time'], backend_position=message['time'], duration=message['duration'],
                                                 paused=not message['playing'], ended=message.get('ended', False),
                                                 volume=message.get('volume', .75), updated_at=now, connected_at=now)
            except (ValueError, KeyError):
                self._error = 'macOS 音频引擎返回无效状态。'

    def _command(self, command):
        try:
            self._proc.stdin.write(command+'\n')
            self._proc.stdin.flush()
        except (OSError, ValueError) as exc:
            raise RuntimeError('macOS 音频引擎通信失败。') from exc

    def poll(self):
        with self._lock:
            state, error = replace(self._state), self._error
        if self._proc.poll() is not None:
            raise RuntimeError('macOS 音频引擎退出：'+'\n'.join(self._stderr))
        if error:
            raise RuntimeError('macOS 音频输出失败：'+error)
        if state.connected_at and time.monotonic()-state.connected_at > 2:
            raise RuntimeError('macOS 音频时钟停止更新。')
        if state.ended:
            state.position = state.duration
        return state

    def play(self):
        if self.poll().ended:
            self.seek(0)
        self._command('play')

    def pause(self):
        self._command('pause')

    def seek(self, position):
        target = min(max(0., position), max(0., self.poll().duration-.01))
        begin = time.monotonic()
        self._command(f'seek {target}')
        while True:
            state = self.poll()
            if state.updated_at > begin and abs(state.position-target) < .25:
                break
            if time.monotonic()-begin > 2:
                raise RuntimeError('macOS 音频跳转没有响应。')
            time.sleep(.01)
        self.last_seek_target, self.last_seek_seconds = target, time.monotonic()-begin

    def set_volume(self, volume):
        self._command(f'volume {min(1., max(0., volume))}')

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            if self._proc.poll() is None:
                try:
                    self._command('quit')
                    self._proc.wait(timeout=1)
                except (RuntimeError, subprocess.TimeoutExpired):
                    self._proc.terminate()
                    try:
                        self._proc.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        self._proc.kill()
                        self._proc.wait()
        finally:
            if self._reader.ident is not None:
                self._reader.join(timeout=1)
            if self._error_reader.ident is not None:
                self._error_reader.join(timeout=1)
            for stream in (self._proc.stdin, self._proc.stdout, self._proc.stderr):
                stream.close()
