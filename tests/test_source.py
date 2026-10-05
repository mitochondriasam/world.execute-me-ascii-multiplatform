"""Source rendering must run without audio, a terminal or platform imports."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from player import Canvas, Film, crop, width

CASES = [(67.3, 'If I can make you happy', '如果我能让你快乐'),
         (124.2, 'Then maybe', '那么也许你离开时不会让我如此'),
         (159.85, 'TROIS', '三'), (183.2, 'Question me', '问我吧，我能回答关于')]


class SourceTests(unittest.TestCase):
    def invoke(self, *args, root=ROOT, cwd=None, utf8=False):
        env = dict(os.environ, PYTHONUTF8='0', PYTHONIOENCODING='gbk')
        command = [sys.executable, *(['-X', 'utf8'] if utf8 else []), '-B',
                   str(root/'player.py'), *map(str, args)]
        result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8'))
        return result.stdout.decode('utf-8', errors='strict')

    def test_help_requires_no_audio_or_terminal(self):
        self.assertIn('--snapshot', self.invoke('--help'))

    def test_bilingual_snapshots_in_unrelated_workdir_and_both_utf8_modes(self):
        with tempfile.TemporaryDirectory() as work:
            for utf8 in (False, True):
                for seconds, english, chinese in CASES:
                    with self.subTest(seconds=seconds, utf8=utf8):
                        output = self.invoke('--snapshot', seconds, '--plain', '--width', 125,
                                             '--height', 45, cwd=work, utf8=utf8)
                        self.assertIn(english, output)
                        self.assertIn(chinese, output)
                        self.assertNotIn('\x1b', output)
                        self.assertEqual(len(output.splitlines()), 45)
                        self.assertTrue(all(width(line) == 125 for line in output.splitlines()))

    def test_chinese_and_space_source_path(self):
        with tempfile.TemporaryDirectory() as work:
            copied = Path(work)/'中文 source directory'
            copied.mkdir()
            for name in ('player.py', 'scenes.py', 'config.json', 'lyrics.json', 'spectrum.json'):
                shutil.copyfile(ROOT/name, copied/name)
            # New platform modules are included when the source layout grows.
            for name in ('audio_backends', 'terminal_backends'):
                if (ROOT/name).is_dir():
                    shutil.copytree(ROOT/name, copied/name, ignore=shutil.ignore_patterns('__pycache__'))
            output = self.invoke('--snapshot', 67.3, '--plain', root=copied, cwd=work)
            self.assertIn('如果我能让你快乐', output)

    def test_scene_boundaries_at_minimum_size(self):
        film = Film()
        for seconds in (0, 16, 29.709, 74.045, 110.9, 125.708, 159.85, 177.246, 192.5, 211.9):
            with self.subTest(seconds=seconds):
                lines = film.render(seconds, 64, 24).plain().splitlines()
                self.assertEqual(len(lines), 24)
                self.assertTrue(all(width(line) == 64 for line in lines))

    def test_small_window_notice(self):
        output = self.invoke('--snapshot', 67.3, '--plain', '--width', 63, '--height', 23)
        self.assertIn('minimum 64 x 24', output)
        self.assertIn('请放大窗口', output)

    def test_wide_character_edge_does_not_overrun_canvas(self):
        canvas = Canvas(5, 1)
        canvas.put(3, 0, '中')
        canvas.put(5, 0, '文')
        self.assertEqual(width(canvas.plain()), 5)
        self.assertEqual(crop('A中文B', 4), 'A中')


if __name__ == '__main__':
    unittest.main()
