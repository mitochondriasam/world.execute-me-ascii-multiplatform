"""Real Windows Media Engine controls. Silent PCM; no external player."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from audio_backends import create_audio
from audio_backends.windows_native import WindowsNativeAudio, flac_duration


@unittest.skipUnless(sys.platform == 'win32', 'Windows native audio requires Windows')
class NativeTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='native-tests-')
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name)/'中文 silent audio.wav'
        with wave.open(str(self.path), 'wb') as output:
            output.setnchannels(2)
            output.setsampwidth(2)
            output.setframerate(44100)
            output.writeframes(b'\0'*4*44100*3)

    def audio(self):
        audio = WindowsNativeAudio(self.path)
        self.addCleanup(audio.close)
        audio.set_volume(0.)
        return audio

    def test_default_uses_native_without_starting_external_process(self):
        with patch('subprocess.Popen', side_effect=AssertionError('external player invoked')):
            audio = create_audio(self.path)
            try:
                self.assertEqual(audio.name, 'windows-native')
                self.assertAlmostEqual(audio.poll().duration, 3., delta=.001)
            finally:
                audio.close()

    def test_play_pause_long_idle_seek_volume_eof_replay_and_cleanup(self):
        audio = self.audio()
        self.assertTrue(audio.poll().paused)
        audio.play()
        time.sleep(.4)
        self.assertGreater(audio.poll().position, .05)
        audio.pause()
        frozen = audio.poll().position
        time.sleep(2.2)
        self.assertAlmostEqual(audio.poll().position, frozen, delta=.02)
        audio.seek(1.234)
        self.assertAlmostEqual(audio.poll().position, 1.234, delta=.01)
        self.assertTrue(audio.poll().paused)
        audio.play()
        time.sleep(.25)
        audio.seek(.75)
        self.assertAlmostEqual(audio.poll().position, .75, delta=.1)
        self.assertFalse(audio.poll().paused)
        audio.set_volume(.35)
        self.assertAlmostEqual(audio.poll().volume, .35, delta=.001)
        audio.set_volume(0.)
        audio.pause()
        audio.seek(2.95)
        audio.play()
        deadline = time.monotonic()+3.
        while not audio.poll().ended and time.monotonic() < deadline:
            time.sleep(.02)
        self.assertTrue(audio.poll().ended)
        self.assertAlmostEqual(audio.poll().position, 3., delta=.001)
        audio.play()
        time.sleep(.3)
        self.assertFalse(audio.poll().ended)
        self.assertGreater(audio.poll().position, 0.)
        self.assertLess(audio.poll().position, 1.)
        audio.close()
        audio.close()
        self.assertFalse(audio._engine)
        self.assertFalse(audio._com)
        self.assertFalse(audio._mf)
        self.assertEqual(audio._notify.refs, 1)
        with self.assertRaisesRegex(RuntimeError, '已关闭'):
            audio.poll()

    def test_invalid_media_and_partial_initialization_release_resources(self):
        invalid = Path(self.folder.name)/'bad.flac'
        invalid.write_bytes(b'not audio')
        with self.assertRaisesRegex(RuntimeError, 'Windows 原生音频'):
            WindowsNativeAudio(invalid)
        # Native COM/MF have already started when the callback constructor fails.
        with patch('audio_backends.windows_native.Notification', side_effect=RuntimeError('callback failed')):
            with self.assertRaisesRegex(RuntimeError, 'callback failed'):
                WindowsNativeAudio(self.path)
        self.audio()  # a new engine still works after both failure paths

    def test_missing_file_null_output_and_nonfinite_controls(self):
        with self.assertRaisesRegex(RuntimeError, '找不到音频'):
            WindowsNativeAudio(Path(self.folder.name)/'missing.flac')
        with self.assertRaisesRegex(RuntimeError, '系统音频输出'):
            WindowsNativeAudio(self.path, output='null')
        audio = self.audio()
        for value in (float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                audio.seek(value)
            with self.assertRaises(ValueError):
                audio.set_volume(value)

    def test_cross_thread_calls_rejected_before_native_invocation(self):
        audio = self.audio()
        errors = []
        def worker():
            for operation in (audio.poll, audio.close):
                try:
                    operation()
                except RuntimeError as exc:
                    errors.append(str(exc))
        thread = threading.Thread(target=worker)
        thread.start()
        thread.join()
        self.assertEqual(len(errors), 2)
        self.assertTrue(audio.poll().paused)

    def test_cli_default_native_report_from_unrelated_directory(self):
        report = Path(self.folder.name)/'播放报告.json'
        result = subprocess.run([sys.executable, '-B', str(ROOT/'player.py'), '--headless',
                                 '--autoplay', '--audio', str(self.path), '--stop-after', '.35',
                                 '--report', str(report)], cwd=self.folder.name,
                                capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8'))
        data = json.loads(report.read_text(encoding='utf-8'))
        self.assertEqual(data['backend'], 'windows-native')
        self.assertEqual(data['exit_reason'], 'stop-after')
        self.assertGreaterEqual(data['last_time'], .35)
        self.assertEqual(data['cleanup_errors'], [])

    def test_native_decode_cache_and_failure_cleanup(self):
        # Exercise native Source Reader with known PCM input; preparing this
        # fixture requires no external encoder. Actual FLAC has a separate probe.
        with patch('audio_backends.windows_native.flac_duration', return_value=3.):
            audio = self.audio()
        folder = Path(audio._scratch.name)
        with wave.open(str(folder/'audio.wav'), 'rb') as output:
            self.assertEqual(output.getnframes(), 132300)
        audio.close()
        self.assertFalse(folder.exists())
        temporary = []
        original = tempfile.TemporaryDirectory
        def record(*args, **kwargs):
            directory = original(*args, **kwargs)
            temporary.append(Path(directory.name))
            return directory
        with patch('audio_backends.windows_native.flac_duration', return_value=4.), \
             patch('audio_backends.windows_native.tempfile.TemporaryDirectory', side_effect=record):
            with self.assertRaisesRegex(RuntimeError, '样本数'):
                WindowsNativeAudio(self.path)
        self.assertTrue(temporary)
        self.assertTrue(all(not path.exists() for path in temporary))


class FlacMetadataTests(unittest.TestCase):
    def test_content_sniffing_sample_precision_and_truncation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'wrong-name.mp3'
            packed = (44100 << 44) | (1 << 41) | (15 << 36) | 9345084
            block = b'\0'*10 + packed.to_bytes(8, 'big') + b'\0'*16
            path.write_bytes(b'fLaC\x80\x00\x00\x22'+block)
            self.assertAlmostEqual(flac_duration(path), 211.9066666667, places=8)
            path.write_bytes(b'fLaC\x80\x00\x00\x22'+block[:10])
            self.assertIsNone(flac_duration(path))
            path.write_bytes(b'not flac')
            self.assertIsNone(flac_duration(path))


if __name__ == '__main__':
    unittest.main()
