"""Real mpv controls, using generated PCM audio and null output (no speakers)."""
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from audio_backends.mpv import MpvAudio, find_mpv


class DiscoveryTests(unittest.TestCase):
    def test_explicit_missing_executable_is_actionable(self):
        with self.assertRaisesRegex(RuntimeError, '指定的 mpv'):
            find_mpv(str(ROOT/'missing-mpv.exe'))

    def test_missing_audio_is_rejected_before_spawn(self):
        with patch('audio_backends.mpv.subprocess.Popen') as popen:
            with self.assertRaisesRegex(RuntimeError, '找不到音频'):
                MpvAudio(ROOT/'missing-audio.flac')
            popen.assert_not_called()


class MpvTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.executable = find_mpv()
        except RuntimeError as exc:
            raise unittest.SkipTest(str(exc))

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='mv-tests-')
        self.addCleanup(self.folder.cleanup)
        self.audio = Path(self.folder.name)/'中文 audio with spaces.wav'
        with wave.open(str(self.audio), 'wb') as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(8000)
            output.writeframes(b'\0\0'*32000)

    def backend(self):
        audio = MpvAudio(self.audio, executable=self.executable, output='null')
        self.addCleanup(audio.close)
        return audio

    def test_play_pause_long_idle_seek_volume_eof_and_replay(self):
        audio = self.backend()
        self.assertAlmostEqual(audio.poll().duration, 4., delta=.01)
        self.assertTrue(audio.poll().paused)
        audio.play()
        time.sleep(.25)
        self.assertGreater(audio.poll().position, .1)
        audio.pause()
        frozen = audio.poll().position
        # This exceeds the old player's two-second stale-position timeout.
        time.sleep(2.2)
        state = audio.poll()
        self.assertTrue(state.paused)
        self.assertAlmostEqual(state.position, frozen, delta=.03)
        self.assertLess(time.monotonic()-state.connected_at, .1)
        audio.seek(2.)
        self.assertAlmostEqual(audio.poll().position, 2., delta=.05)
        self.assertLess(audio.last_seek_seconds, .3)
        audio.play()
        time.sleep(.15)
        state = audio.poll()
        self.assertGreater(state.backend_position, 2.)
        self.assertAlmostEqual(state.position, state.backend_position, delta=.001)
        audio.seek(1.)
        self.assertAlmostEqual(audio.poll().position, 1., delta=.1)
        audio.set_volume(.35)
        self.assertAlmostEqual(audio.poll().volume, .35, delta=.001)
        audio.pause()
        audio.seek(3.75)
        audio.play()
        deadline = time.monotonic()+3
        while not audio.poll().ended and time.monotonic() < deadline:
            time.sleep(.02)
        self.assertTrue(audio.poll().ended)
        self.assertAlmostEqual(audio.poll().position, 4., delta=.01)
        audio.play()
        time.sleep(.15)
        state = audio.poll()
        self.assertFalse(state.ended)
        self.assertFalse(state.paused)
        self.assertGreater(state.position, .05)
        self.assertLess(state.position, 1.)
        proc, transport = audio._proc, audio._transport
        audio.close()
        audio.close()
        self.assertIsNotNone(proc.poll())
        if sys.platform == 'win32':
            self.assertIsNone(transport.handle)

    def test_process_failure_is_not_eof_and_close_reaps_it(self):
        audio = self.backend()
        audio._proc.kill()
        audio._proc.wait(timeout=2)
        with self.assertRaisesRegex(RuntimeError, '意外退出'):
            audio.poll()
        self.assertFalse(audio._state.ended)
        audio.close()

    def test_idle_native_read_timeout_can_be_cancelled_then_reused(self):
        audio = self.backend()
        audio.poll()
        for _ in range(20):
            try:
                audio._buffer += audio._transport.receive(.05)
            except TimeoutError:
                break
        else:
            self.fail('paused IPC did not become idle')
        self.assertTrue(audio.poll().paused)

    def test_reader_thread_start_failure_reaps_already_started_child(self):
        processes = []
        real_popen = subprocess.Popen
        def record(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            processes.append(process)
            return process
        with patch('audio_backends.mpv.subprocess.Popen', side_effect=record), \
             patch('audio_backends.mpv.threading.Thread.start', side_effect=RuntimeError('thread unavailable')):
            with self.assertRaisesRegex(RuntimeError, 'thread unavailable'):
                MpvAudio(self.audio, executable=self.executable, output='null')
        self.assertIsNotNone(processes[0].poll())

    def test_invalid_media_startup_cleans_up_child(self):
        invalid = Path(self.folder.name)/'not-a-song.flac'
        invalid.write_bytes(b'not audio')
        processes = []
        real_popen = subprocess.Popen

        def record(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            processes.append(process)
            return process

        with patch('audio_backends.mpv.subprocess.Popen', side_effect=record):
            with self.assertRaisesRegex(RuntimeError, 'mpv'):
                MpvAudio(invalid, executable=self.executable, output='null')
        self.assertEqual(len(processes), 1)
        self.assertIsNotNone(processes[0].poll())

    def test_cli_headless_render_report_and_utf8_workdir(self):
        report = Path(self.folder.name)/'播放 report.json'
        result = subprocess.run([sys.executable, '-B', str(ROOT/'player.py'), '--headless',
                                 '--autoplay', '--backend', 'mpv', '--audio', str(self.audio), '--audio-output', 'null',
                                 '--stop-after', '.35', '--report', str(report)],
                                cwd=self.folder.name, capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8'))
        self.assertEqual(result.stdout, b'')
        import json
        data = json.loads(report.read_text(encoding='utf-8'))
        self.assertGreater(data['frames'], 0)
        self.assertEqual(data['backend'], 'mpv')
        self.assertEqual(data['exit_reason'], 'stop-after')
        self.assertGreaterEqual(data['last_time'], .35)


if __name__ == '__main__':
    unittest.main()
