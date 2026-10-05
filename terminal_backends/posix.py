"""Keep the existing controlling-terminal behavior on macOS and Linux."""
import os
import select
import sys
import termios
import time
import tty

from . import ENTER, LEAVE, key_event


class PosixTerminal:
    def __init__(self):
        self.input = sys.stdin
        self.output = None
        self.original = None
        self.active = False
        self.buffer = ''

    def __enter__(self):
        if not self.input.isatty():
            raise RuntimeError('实时播放需要交互终端；自动检查请使用 --headless。')
        try:
            descriptor = os.open('/dev/tty', os.O_RDWR)
            try:
                self.output = os.fdopen(descriptor, 'w', encoding='utf-8', buffering=1)
            except BaseException:
                os.close(descriptor)
                raise
            self.original = termios.tcgetattr(self.input.fileno())
            tty.setcbreak(self.input.fileno())
            self.active = True
            self.output.write(ENTER)
            self.output.flush()
            return self
        except BaseException:
            self.close()
            raise

    def close(self):
        errors = []
        try:
            if self.active:
                try:
                    self.output.write(LEAVE)
                    self.output.flush()
                except (OSError, ValueError):
                    pass
        finally:
            self.active = False
            try:
                if self.original is not None:
                    try:
                        termios.tcsetattr(self.input.fileno(), termios.TCSADRAIN, self.original)
                    except (OSError, termios.error, ValueError) as exc:
                        errors.append(exc)
            finally:
                self.original = None
                if self.output:
                    try:
                        self.output.close()
                    except (OSError, ValueError) as exc:
                        errors.append(exc)
                    self.output = None
        for error in errors:
            try:
                print(f'终端恢复失败：{error}', file=sys.stderr)
            except (OSError, ValueError):
                pass

    def __exit__(self, *args):
        self.close()
        return False

    def size(self):
        size = os.get_terminal_size(self.input.fileno())
        return size.columns, size.lines

    def draw(self, canvas, clear=False):
        self.output.write(('\x1b[2J' if clear else '')+canvas.ansi())
        self.output.flush()

    def read_events(self, timeout):
        if select.select([self.input], [], [], timeout)[0]:
            data = os.read(self.input.fileno(), 128)
            if not data:
                return ['QUIT']
            self.buffer += data.decode('utf-8', errors='ignore')
            if self.buffer.startswith('\x1b') and select.select([self.input], [], [], .035)[0]:
                self.buffer += os.read(self.input.fileno(), 32).decode('utf-8', errors='ignore')
        events = []
        while self.buffer:
            arrow = next((seq for seq in ('\x1b[C', '\x1b[D', '\x1bOC', '\x1bOD') if self.buffer.startswith(seq)), None)
            if arrow:
                events.append('RIGHT' if arrow[-1] == 'C' else 'LEFT')
                self.buffer = self.buffer[len(arrow):]
            else:
                events.append(key_event(self.buffer[0]))
                self.buffer = self.buffer[1:]
        return events
