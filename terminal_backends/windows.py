"""Native console modes and msvcrt input, including extended arrow keys."""
import ctypes
from ctypes import wintypes
import msvcrt
import os
import sys
import time

from . import ENTER, LEAVE, key_event


class WindowsTerminal:
    def __init__(self):
        self.input, self.output = sys.stdin, sys.stdout
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        self.api.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        self.api.GetConsoleMode.restype = wintypes.BOOL
        self.api.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.api.SetConsoleMode.restype = wintypes.BOOL
        self.original = []
        self.active = False
        self.extended = False

    def _set_mode(self, handle, mode):
        if not self.api.SetConsoleMode(handle, mode):
            raise ctypes.WinError(ctypes.get_last_error())

    def __enter__(self):
        if not self.input.isatty() or not self.output.isatty():
            raise RuntimeError('实时播放需要 Windows Terminal 的交互输入和输出；'
                               '快照可重定向，自动检查请使用 --headless。')
        try:
            for stream, is_output in ((self.input, False), (self.output, True)):
                handle = msvcrt.get_osfhandle(stream.fileno())
                mode = wintypes.DWORD()
                if not self.api.GetConsoleMode(handle, ctypes.byref(mode)):
                    raise RuntimeError('无法读取 Windows 控制台模式；请在 Windows Terminal 中运行。')
                self.original.append((handle, mode.value))
                new_mode = (mode.value | 4) if is_output else ((mode.value | 0x80) & ~(2 | 4 | 0x40 | 0x200))
                self._set_mode(handle, new_mode)
            self.active = True
            self.output.write(ENTER)
            self.output.flush()
            return self
        except BaseException:
            self.close()
            raise

    def close(self):
        errors = []
        if self.active:
            try:
                self.output.write(LEAVE)
                self.output.flush()
            except (OSError, ValueError) as exc:
                errors.append(exc)
        self.active = False
        for handle, mode in reversed(self.original):
            try:
                self._set_mode(handle, mode)
            except OSError as exc:
                errors.append(exc)
        self.original.clear()
        for error in errors:
            try:
                print(f'终端恢复失败：{error}', file=sys.stderr)
            except (OSError, ValueError):
                pass

    def __exit__(self, *args):
        self.close()
        return False

    def size(self):
        size = os.get_terminal_size(self.output.fileno())
        return size.columns, size.lines

    def draw(self, canvas, clear=False):
        self.output.write(('\x1b[2J' if clear else '')+canvas.ansi())
        self.output.flush()

    def read_events(self, timeout):
        deadline = time.monotonic()+timeout
        events = []
        while True:
            while msvcrt.kbhit():
                key = msvcrt.getwch()
                if self.extended:
                    self.extended = False
                    event = {'K': 'LEFT', 'M': 'RIGHT'}.get(key)
                    if event:
                        events.append(event)
                elif key in ('\x00', '\xe0'):
                    self.extended = True
                else:
                    events.append(key_event(key))
            if events or time.monotonic() >= deadline:
                return events
            time.sleep(min(.01, max(0, deadline-time.monotonic())))
