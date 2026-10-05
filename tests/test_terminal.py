"""Windows mode restoration and all control events without a visible console."""
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from terminal_backends import key_event


class KeyTests(unittest.TestCase):
    def test_common_controls(self):
        for key, expected in [(' ', 'SPACE'), ('\r', 'ENTER'), ('\x1b', 'QUIT'),
                              ('q', 'QUIT'), ('Q', 'QUIT'), ('r', 'R'), ('h', 'H'),
                              ('=', '+'), ('[', '['), (']', ']'), (',', ','), ('.', '.')]:
            self.assertEqual(key_event(key), expected)


@unittest.skipUnless(sys.platform == 'win32', 'Windows native terminal tests')
class WindowsTerminalTests(unittest.TestCase):
    def backend(self):
        from terminal_backends.windows import WindowsTerminal
        return WindowsTerminal()

    def test_redirected_console_is_rejected_without_mode_changes(self):
        terminal = self.backend()
        terminal.input = io.StringIO()
        terminal.output = io.StringIO()
        with self.assertRaisesRegex(RuntimeError, '交互输入和输出'):
            terminal.__enter__()
        self.assertEqual(terminal.original, [])

    def test_extended_keys_split_across_polls_and_all_ascii_controls(self):
        terminal = self.backend()
        from collections import deque
        keys = deque(['\xe0'])
        with patch('terminal_backends.windows.msvcrt.kbhit', side_effect=lambda: bool(keys)), \
             patch('terminal_backends.windows.msvcrt.getwch', side_effect=lambda: keys.popleft()):
            self.assertEqual(terminal.read_events(0), [])
            keys.extend(['K', '\x00', 'M', ' ', '\r', 'R', 'Q', 'H', '1', '2', '3', '4', '5', '[', ']', ',', '.', '+', '-', '\x1b'])
            self.assertEqual(terminal.read_events(0), ['LEFT', 'RIGHT', 'SPACE', 'ENTER', 'R', 'QUIT', 'H',
                             '1', '2', '3', '4', '5', '[', ']', ',', '.', '+', '-', 'QUIT'])

    def test_each_mode_is_restored_even_if_ansi_output_fails(self):
        terminal = self.backend()
        terminal.original = [(11, 7), (12, 23)]
        terminal.active = True
        class BrokenOutput(io.StringIO):
            def write(self, value):
                raise OSError('closed console')
        terminal.output = BrokenOutput()
        with patch.object(terminal, '_set_mode') as restore, patch('sys.stderr', io.StringIO()):
            terminal.close()
            self.assertEqual([call.args for call in restore.call_args_list], [(12, 23), (11, 7)])
            terminal.close()
            self.assertEqual(restore.call_count, 2)

    def test_partial_mode_initialization_restores_both_original_modes(self):
        terminal = self.backend()
        terminal.input = unittest.mock.Mock()
        terminal.output = unittest.mock.Mock()
        terminal.input.fileno.return_value = 11
        terminal.output.fileno.return_value = 12
        modes = {11: 0x207, 12: 0x03}
        def read_mode(handle, output):
            output._obj.value = modes[handle]
            return True
        changed = []
        def set_mode(handle, mode):
            changed.append((handle, mode))
            if handle == 12 and mode == 7:
                raise OSError('VT unavailable')
        with patch('terminal_backends.windows.msvcrt.get_osfhandle', side_effect=lambda descriptor: descriptor), \
             patch.object(terminal.api, 'GetConsoleMode', side_effect=read_mode), \
             patch.object(terminal, '_set_mode', side_effect=set_mode):
            with self.assertRaisesRegex(OSError, 'VT unavailable'):
                terminal.__enter__()
        self.assertEqual(changed[-2:], [(12, 3), (11, 0x207)])
        self.assertEqual(terminal.original, [])


if __name__ == '__main__':
    unittest.main()
