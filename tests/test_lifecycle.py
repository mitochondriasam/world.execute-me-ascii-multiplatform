"""Failures after partial initialization must preserve errors and restore resources."""
from argparse import Namespace
from pathlib import Path
import signal
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from audio_backends import AudioState
from player import run


class Terminal:
    def __init__(self):
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def size(self):
        return 120, 40

    def draw(self, *args, **kwargs):
        raise RuntimeError('console disconnected')


class LifecycleTests(unittest.TestCase):
    def args(self):
        return Namespace(audio=str(ROOT/'config.json'), offset=None, autoplay=True, paused=False,
                         start=0., report=None, headless=False, width=120, height=40,
                         backend='mpv', mpv=None, audio_output='null', stop_after=None, fps=24)

    def test_audio_constructor_failure_restores_entered_terminal_and_signals(self):
        terminal = Terminal()
        original = signal.getsignal(signal.SIGTERM)
        with patch('terminal_backends.create_terminal', return_value=terminal), \
             patch('audio_backends.create_audio', side_effect=RuntimeError('audio init failed')):
            with self.assertRaisesRegex(RuntimeError, 'audio init failed'):
                run(self.args(), Mock(config={}))
        self.assertTrue(terminal.closed)
        self.assertIs(signal.getsignal(signal.SIGTERM), original)

    def test_cleanup_error_does_not_hide_playback_error_or_prevent_terminal_restore(self):
        terminal = Terminal()
        audio = Mock(name='audio')
        audio.name = 'mpv'
        audio.poll.return_value = AudioState(duration=4.)
        audio.close.side_effect = RuntimeError('cleanup failed')
        original = signal.getsignal(signal.SIGTERM)
        with patch('terminal_backends.create_terminal', return_value=terminal), \
             patch('audio_backends.create_audio', return_value=audio), patch('sys.stderr'):
            with self.assertRaisesRegex(RuntimeError, 'console disconnected'):
                run(self.args(), Mock(config={}))
        audio.close.assert_called_once()
        self.assertTrue(terminal.closed)
        self.assertIs(signal.getsignal(signal.SIGTERM), original)

    def test_terminal_constructor_failure_does_not_start_audio(self):
        terminal = Mock()
        terminal.__enter__ = Mock(side_effect=RuntimeError('VT unavailable'))
        terminal.__exit__ = Mock()
        with patch('terminal_backends.create_terminal', return_value=terminal), \
             patch('audio_backends.create_audio') as audio:
            with self.assertRaisesRegex(RuntimeError, 'VT unavailable'):
                run(self.args(), Mock(config={}))
            audio.assert_not_called()


if __name__ == '__main__':
    unittest.main()
