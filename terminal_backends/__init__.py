"""Platform terminal selection, imported only for playback."""
import os
import time

ENTER = '\x1b[?1049h\x1b[?25l\x1b[?7l\x1b[2J'
LEAVE = '\x1b[0m\x1b[?7h\x1b[?25h\x1b[?1049l'


def key_event(key):
    return {' ': 'SPACE', '\r': 'ENTER', '\n': 'ENTER', '\x1b': 'QUIT',
            '\x03': 'QUIT', 'q': 'QUIT', 'Q': 'QUIT',
            'r': 'R', 'h': 'H', '=': '+'}.get(key, key)


class HeadlessTerminal:
    def __init__(self, width, height):
        self.dimensions = (width, height)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def size(self):
        return self.dimensions

    def draw(self, canvas, clear=False):
        pass

    def read_events(self, timeout):
        time.sleep(timeout)
        return []


def create_terminal(*, headless=False, width=120, height=40):
    if headless:
        return HeadlessTerminal(width, height)
    if os.name == 'nt':
        from .windows import WindowsTerminal
        return WindowsTerminal()
    from .posix import PosixTerminal
    return PosixTerminal()
