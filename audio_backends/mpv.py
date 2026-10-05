"""mpv JSON IPC; no third-party Python modules and no wall-clock song timing."""
from collections import deque
from dataclasses import replace
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import uuid

from . import AudioState
from .transport import connect


def find_mpv(explicit=None):
    def direct_executable(path):
        path = Path(path)
        # The Windows console shim can spawn mpv.exe. Own the actual player
        # process so terminating a failed backend cannot leave its child behind.
        sibling = path.with_name('mpv.exe')
        if path.name.lower() == 'mpv.com' and sibling.is_file():
            path = sibling
        return str(path.resolve())

    configured = explicit or os.environ.get('MPV_PATH')
    if configured:
        path = Path(configured).expanduser()
        if path.is_file():
            return direct_executable(path)
        resolved = shutil.which(configured)
        if resolved:
            return direct_executable(resolved)
        raise RuntimeError(f'找不到指定的 mpv：{configured}')
    for command in ('mpv', 'mpv.exe'):
        found = shutil.which(command)
        if found:
            return direct_executable(found)
    if os.name == 'nt':
        for variable in ('ProgramFiles', 'ProgramFiles(x86)', 'LOCALAPPDATA'):
            parent = os.environ.get(variable)
            if parent:
                for relative in ('MPV Player/mpv.exe', 'mpv/mpv.exe', 'Programs/mpv/mpv.exe'):
                    candidate = Path(parent)/relative
                    if candidate.is_file():
                        return str(candidate)
    raise RuntimeError('找不到 mpv。Windows 可运行 winget install --id shinchiro.mpv --exact；'
                       '或使用 --mpv / MPV_PATH 指定完整路径。')


class MpvAudio:
    name = 'mpv'
    properties = {'time-pos': 'position', 'duration': 'duration', 'pause': 'paused',
                  'paused-for-cache': 'buffering', 'seeking': 'seeking',
                  'eof-reached': 'ended', 'volume': 'volume'}

    def __init__(self, path, executable=None, output='auto', timeout=2.0):
        self._state = AudioState()
        self._proc = None
        self._transport = None
        self._scratch = None
        self._closed = False
        self._reader = None
        self._errors = deque(maxlen=30)
        self._buffer = b''
        self._request_id = 0
        self._failure = ''
        self._playback_restarts = 0
        self._paused_seek_position = None
        self.timeout = timeout
        self.last_seek_seconds = None
        self.last_seek_target = None
        path = Path(path).expanduser().resolve()
        if not path.is_file():
            raise RuntimeError(f'找不到音频：{path}；请使用 --audio 指定音频文件。')
        executable = find_mpv(executable)
        token = 'world-execute-' + uuid.uuid4().hex
        if os.name == 'nt':
            address = '\\\\.\\pipe\\' + token
        else:
            self._scratch = tempfile.TemporaryDirectory(prefix='mv-ipc-')
            address = str(Path(self._scratch.name)/'mpv.sock')
        try:
            command = [executable, '--no-config', '--load-scripts=no', '--no-terminal',
                       '--input-terminal=no', '--no-video', '--no-audio-display',
                       '--idle=yes', '--keep-open=yes', '--pause=yes', '--volume=75',
                       '--audio-file-auto=no', f'--input-ipc-server={address}']
            if output == 'null':
                command.append('--ao=null')
            self._proc = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                          stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                          creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            self._reader = threading.Thread(target=self._read_errors, daemon=True)
            self._reader.start()
            deadline = time.monotonic()+8
            while self._transport is None:
                self._check_process()
                try:
                    self._transport = connect(address)
                except OSError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError('mpv IPC 未能建立连接：' + self._diagnostic())
                    time.sleep(.02)
            for number, name in enumerate(self.properties, 1):
                self._request(['observe_property', number, name])
            # Connect first so decode/output errors cannot be emitted before a
            # client is listening. JSON also avoids any filename option parsing.
            self._request(['loadfile', str(path)])
            while True:
                self.poll()
                if self._state.duration > 0 and self._state.updated_at:
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError('mpv 未加载有效音频/时长：' + self._diagnostic())
                time.sleep(.02)
        except BaseException:
            self.close()
            raise

    def _read_errors(self):
        for line in iter(self._proc.stderr.readline, b''):
            self._errors.append(line.decode('utf-8', errors='replace').strip())

    def _diagnostic(self):
        return '\n'.join(self._errors) or '请检查音频文件和声音输出设备。'

    def _check_process(self):
        if self._closed:
            raise RuntimeError('mpv 音频后端已关闭')
        if self._proc.poll() is not None:
            raise RuntimeError('mpv 音频进程意外退出：' + self._diagnostic())
        if self._failure:
            raise RuntimeError(self._failure)

    def _event(self, message):
        if message.get('event') == 'property-change':
            name, value = message.get('name'), message.get('data')
            if value is not None and name in self.properties:
                if name in ('time-pos', 'duration', 'volume'):
                    if not isinstance(value, (int, float)) or not math.isfinite(value):
                        return
                    value = float(value)
                    if name == 'volume':
                        value /= 100
                setattr(self._state, self.properties[name], value)
                if name == 'time-pos':
                    self._state.updated_at = time.monotonic()
        elif message.get('event') == 'playback-restart':
            self._playback_restarts += 1
        elif message.get('event') == 'end-file':
            if message.get('reason') == 'error':
                self._failure = 'mpv 无法播放音频：' + str(message.get('file_error', '解码或音频输出失败'))
            elif message.get('reason') == 'eof':
                self._state.ended = True

    def _request(self, command, *, allow_unavailable=False, timeout=None):
        self._check_process()
        self._request_id += 1
        request_id = self._request_id
        limit = self.timeout if timeout is None else timeout
        deadline = time.monotonic()+limit
        payload = json.dumps({'command': command, 'request_id': request_id}, ensure_ascii=False).encode('utf-8')+b'\n'
        try:
            self._transport.send(payload, limit)
            while True:
                while b'\n' in self._buffer:
                    line, self._buffer = self._buffer.split(b'\n', 1)
                    message = json.loads(line.decode('utf-8'))
                    self._state.connected_at = time.monotonic()
                    if message.get('request_id') == request_id:
                        self._check_process()
                        error = message.get('error', 'success')
                        if error != 'success':
                            if allow_unavailable and error == 'property unavailable':
                                return None
                            raise RuntimeError(f'mpv 命令 {command[0]} 失败：{error}')
                        return message.get('data')
                    self._event(message)
                    self._check_process()
                remaining = deadline-time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('mpv 请求响应超时')
                self._buffer += self._transport.receive(remaining)
                if len(self._buffer) > 1024*1024:
                    raise RuntimeError('mpv IPC 消息过大')
        except (OSError, ValueError, ConnectionError) as exc:
            raise RuntimeError(f'mpv IPC 通信失败：{exc}') from exc

    def poll(self):
        # A reply is also a heartbeat when paused: lack of position events is harmless.
        position = self._request(['get_property', 'time-pos'], allow_unavailable=True)
        # Control events can trail command acknowledgements. Read authoritative
        # pause/EOF/seek flags before constructing a snapshot, rather than allowing
        # an older observer notification to overwrite a completed command.
        for property_name, field in (('pause', 'paused'), ('eof-reached', 'ended'), ('seeking', 'seeking')):
            value = self._request(['get_property', property_name], allow_unavailable=True)
            if isinstance(value, bool):
                setattr(self._state, field, value)
        if isinstance(position, (int, float)) and math.isfinite(position):
            self._state.backend_position = float(position)
            # Some audio drivers retain their old buffered delay after a paused
            # seek. Use the acknowledged exact seek target until playback resumes.
            self._state.position = (self._paused_seek_position if self._state.paused and
                                    self._paused_seek_position is not None else float(position))
            self._state.updated_at = time.monotonic()
        if self._state.ended:
            self._state.position = self._state.duration
            self._state.paused = True
        return replace(self._state)

    def play(self):
        if self._state.ended:
            self.seek(0)
        self._request(['set_property', 'pause', False])
        self._state.paused = False
        self._paused_seek_position = None

    def pause(self):
        self._request(['set_property', 'pause', True])
        self._state.paused = True

    def seek(self, position):
        target = min(max(0.0, float(position)), max(0.0, self._state.duration-.01))
        begin = time.monotonic()
        previous_restart = self._playback_restarts
        self._paused_seek_position = None
        self._request(['seek', target, 'absolute+exact'])
        self._state.ended = False
        deadline = begin+self.timeout
        while True:
            state = self.poll()
            advance = 0. if state.paused else time.monotonic()-begin
            if self._playback_restarts > previous_restart and not state.seeking:
                if state.paused:
                    self._paused_seek_position = target
                    self._state.position = target
                    break
                if target-.025 <= state.position <= target+advance+.025:
                    break
            if time.monotonic() >= deadline:
                raise RuntimeError(f'mpv seek 未恢复到目标位置 {target:.3f}s')
            time.sleep(.01)
        self.last_seek_target = target
        self.last_seek_seconds = time.monotonic()-begin

    def set_volume(self, volume):
        volume = min(1.0, max(0.0, volume))
        self._request(['set_property', 'volume', volume*100])
        self._state.volume = volume

    def close(self):
        if self._closed:
            return
        try:
            if self._transport and self._proc and self._proc.poll() is None:
                try:
                    self._request(['quit'], timeout=.3)
                except Exception:
                    pass
            if self._proc:
                try:
                    self._proc.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    self._proc.terminate()
                    try:
                        self._proc.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        self._proc.kill()
                        self._proc.wait()
        finally:
            self._closed = True
            try:
                if self._transport:
                    self._transport.close()
            finally:
                if self._reader and self._reader.ident is not None:
                    self._reader.join(timeout=1)
                if self._proc and self._proc.stderr:
                    self._proc.stderr.close()
                if self._scratch:
                    self._scratch.cleanup()
