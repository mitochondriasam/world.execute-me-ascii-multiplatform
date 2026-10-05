"""Windows Media Engine through ctypes: no player process or Python packages.

COM signatures and vtable slots follow Microsoft's mfmediaengine.h / mfobjects.h.
Callbacks only record events; engine methods run on the initializing thread.
"""
from collections import deque
import ctypes as C
from dataclasses import replace
import math
from pathlib import Path
import sys
import tempfile
import threading
import time
import uuid
import wave

from . import AudioState


class GUID(C.Structure):
    _fields_ = [('data', C.c_ubyte * 16)]

    @classmethod
    def parse(cls, value):
        return cls.from_buffer_copy(uuid.UUID(value).bytes_le)


PTR = C.c_void_p
HR = C.c_int32
DWORD = C.c_uint32
BOOL = C.c_int32
DOUBLE = C.c_double
UNKNOWN = GUID.parse('00000000-0000-0000-c000-000000000046')
NOTIFY = GUID.parse('fee7c112-e776-42b5-9bbf-0048524e2bd5')
FACTORY = GUID.parse('b44392da-499b-446b-a4cb-005fead0e6d5')
FACTORY_IID = GUID.parse('4d645ace-26aa-4688-9be1-df3516990b93')
CALLBACK = GUID.parse('c60381b8-83a4-41f8-a3d0-de05076849a9')
MAJOR_TYPE = GUID.parse('48eba18e-f8c9-4687-bf11-0a74c9f96a8f')
AUDIO_TYPE = GUID.parse('73647561-0000-0010-8000-00aa00389b71')
SUBTYPE = GUID.parse('f7e34c9a-42e8-4714-b74b-cb29d72c35e5')
PCM_TYPE = GUID.parse('00000001-0000-0010-8000-00aa00389b71')


class WaveFormat(C.Structure):
    _pack_ = 1
    _fields_ = [('tag', C.c_uint16), ('channels', C.c_uint16), ('rate', DWORD),
                ('bytes_per_second', DWORD), ('alignment', C.c_uint16),
                ('bits', C.c_uint16), ('extra', C.c_uint16)]


def checked(hr, operation):
    if hr < 0:
        raise RuntimeError(f'Windows 原生音频：{operation} 失败 (HRESULT 0x{hr & 0xffffffff:08X})。'
                           '请检查媒体文件、音频设备和 Windows Media Foundation 是否可用。')


def invoke(pointer, slot, result, arguments=(), *values):
    table = C.cast(pointer, C.POINTER(C.POINTER(PTR))).contents
    method = C.WINFUNCTYPE(result, PTR, *arguments)(table[slot])
    return method(pointer, *values)


def release(pointer):
    if pointer:
        invoke(pointer, 2, DWORD)
        pointer.value = None


def flac_duration(path):
    """STREAMINFO is exact; Windows' FLAC source can report whole seconds only."""
    with path.open('rb') as source:
        if source.read(4) != b'fLaC':
            return None
        header = source.read(4)
        if len(header) != 4 or header[0] & 0x7f != 0 or int.from_bytes(header[1:], 'big') != 34:
            return None
        info = source.read(34)
        if len(info) != 34:
            return None
        packed = int.from_bytes(info[10:18], 'big')
        rate, samples = packed >> 44, packed & ((1 << 36)-1)
        return samples/rate if rate and samples else None


class Notification:
    """Pin Python callback trampolines for the complete native object lifetime."""
    def __init__(self, kernel):
        self.events = deque()
        self.lock = threading.Lock()
        self.refs = 1
        self.kernel = kernel
        query_type = C.WINFUNCTYPE(HR, PTR, C.POINTER(GUID), C.POINTER(PTR))
        count_type = C.WINFUNCTYPE(DWORD, PTR)
        event_type = C.WINFUNCTYPE(HR, PTR, DWORD, C.c_size_t, DWORD)

        def query(this, iid, output):
            output[0] = None
            if bytes(iid.contents) not in (bytes(UNKNOWN), bytes(NOTIFY)):
                return -2147467262  # E_NOINTERFACE
            output[0] = this
            add_ref(this)
            return 0

        def add_ref(this):
            with self.lock:
                self.refs += 1
                return self.refs

        def drop_ref(this):
            with self.lock:
                self.refs -= 1
                return self.refs

        def event(this, kind, first, second):
            # The stable-state event is a native event HANDLE, not a COM object.
            if kind == 1008:
                self.kernel.SetEvent(PTR(first))
            else:
                with self.lock:
                    self.events.append((kind, first, second))
            return 0

        self.functions = (query_type(query), count_type(add_ref),
                          count_type(drop_ref), event_type(event))
        self.table = (PTR * 4)(*(C.cast(fn, PTR).value for fn in self.functions))
        self.object = (PTR * 1)(C.cast(self.table, PTR).value)
        self.pointer = C.cast(self.object, PTR)

    def drain(self):
        with self.lock:
            events = list(self.events)
            self.events.clear()
            return events


class WindowsNativeAudio:
    name = 'windows-native'

    def __init__(self, path, output='auto', timeout=8.0):
        if sys.platform != 'win32':
            raise RuntimeError('Windows 原生音频后端仅支持 Windows。')
        if output != 'auto':
            raise RuntimeError('Windows 原生后端使用系统音频输出；空输出检查请显式选择 --backend mpv。')
        path = Path(path).expanduser().resolve()
        if not path.is_file():
            raise RuntimeError(f'找不到音频：{path}；请使用 --audio 指定音频文件。')
        self._owner = threading.get_ident()
        self._closed = False
        self._com = False
        self._mf = False
        self._engine = PTR()
        self._attributes = PTR()
        self._factory = PTR()
        self._notify = None
        self._scratch = None
        self._state = AudioState()
        self._precise_duration = flac_duration(path)
        self._failure = None
        self._seeked = 0
        self.timeout = timeout
        self.last_seek_target = None
        self.last_seek_seconds = None
        try:
            self._ole = C.WinDLL('ole32')
            self._automation = C.WinDLL('oleaut32')
            self._platform = C.WinDLL('mfplat')
            kernel = C.WinDLL('kernel32')
            self._ole.CoInitializeEx.argtypes = (PTR, DWORD)
            self._ole.CoInitializeEx.restype = HR
            self._ole.CoCreateInstance.argtypes = (C.POINTER(GUID), PTR, DWORD,
                                                   C.POINTER(GUID), C.POINTER(PTR))
            self._ole.CoCreateInstance.restype = HR
            self._platform.MFStartup.argtypes = (DWORD, DWORD)
            self._platform.MFStartup.restype = HR
            self._platform.MFShutdown.restype = HR
            self._platform.MFCreateAttributes.argtypes = (C.POINTER(PTR), DWORD)
            self._platform.MFCreateAttributes.restype = HR
            self._automation.SysAllocString.argtypes = (C.c_wchar_p,)
            self._automation.SysAllocString.restype = PTR
            self._automation.SysFreeString.argtypes = (PTR,)
            self._automation.SysFreeString.restype = None
            self._ole.CoUninitialize.argtypes = ()
            self._ole.CoUninitialize.restype = None
            kernel.SetEvent.argtypes = (PTR,)
            kernel.SetEvent.restype = BOOL
            checked(self._ole.CoInitializeEx(None, 0), '初始化 COM')
            self._com = True
            checked(self._platform.MFStartup(0x20070, 0), '初始化 Media Foundation')
            self._mf = True
            # Windows' FLAC source rounds its duration and clamps seeks to that
            # rounded end. Decode losslessly to a temporary PCM WAV with native
            # Source Reader so Media Engine gets exact frame counts and seeks.
            if self._precise_duration is not None:
                self._scratch = tempfile.TemporaryDirectory(prefix='world-native-')
                path = self._decode_flac(path, Path(self._scratch.name)/'audio.wav')
            self._notify = Notification(kernel)
            checked(self._platform.MFCreateAttributes(C.byref(self._attributes), 1), '创建属性')
            checked(invoke(self._attributes, 27, HR, (C.POINTER(GUID), PTR),
                           C.byref(CALLBACK), self._notify.pointer), '设置事件回调')
            checked(self._ole.CoCreateInstance(C.byref(FACTORY), None, 1,
                                              C.byref(FACTORY_IID), C.byref(self._factory)), '创建媒体工厂')
            checked(invoke(self._factory, 3, HR, (DWORD, PTR, C.POINTER(PTR)),
                           1, self._attributes, C.byref(self._engine)), '创建音频引擎')
            release(self._attributes)
            release(self._factory)
            self.set_volume(.75)
            source = self._automation.SysAllocString(str(path))
            if not source:
                raise MemoryError('无法分配媒体路径')
            try:
                self._command(6, '打开媒体', (PTR,), source)
            finally:
                self._automation.SysFreeString(source)
            self._command(12, '加载媒体')
            self._wait(lambda: self._value(14, C.c_uint16) >= 3, '加载媒体')
            if not self._value(39, BOOL):
                raise RuntimeError('Windows 原生音频：文件中没有可播放的音轨。')
            self.poll()
        except BaseException as exc:
            try:
                self.close()
            except Exception as cleanup:
                exc.add_note(f'音频初始化后的清理失败：{cleanup}')
            raise

    def _decode_flac(self, source, target):
        reader, media_type, actual_type, format_pointer = PTR(), PTR(), PTR(), PTR()
        readwrite = C.WinDLL('mfreadwrite')
        readwrite.MFCreateSourceReaderFromURL.argtypes = (C.c_wchar_p, PTR, C.POINTER(PTR))
        readwrite.MFCreateSourceReaderFromURL.restype = HR
        self._platform.MFCreateMediaType.argtypes = (C.POINTER(PTR),)
        self._platform.MFCreateMediaType.restype = HR
        self._platform.MFCreateWaveFormatExFromMFMediaType.argtypes = (
            PTR, C.POINTER(PTR), C.POINTER(DWORD), DWORD)
        self._platform.MFCreateWaveFormatExFromMFMediaType.restype = HR
        self._ole.CoTaskMemFree.argtypes = (PTR,)
        self._ole.CoTaskMemFree.restype = None
        audio_stream = 0xfffffffd
        try:
            checked(readwrite.MFCreateSourceReaderFromURL(str(source), None, C.byref(reader)), '打开 FLAC 解码器')
            checked(invoke(reader, 4, HR, (DWORD, BOOL), 0xfffffffe, 0), '取消非音频流')
            checked(invoke(reader, 4, HR, (DWORD, BOOL), audio_stream, 1), '选择音轨')
            checked(self._platform.MFCreateMediaType(C.byref(media_type)), '创建 PCM 类型')
            for key, value in ((MAJOR_TYPE, AUDIO_TYPE), (SUBTYPE, PCM_TYPE)):
                checked(invoke(media_type, 24, HR, (C.POINTER(GUID), C.POINTER(GUID)),
                               C.byref(key), C.byref(value)), '设置 PCM 类型')
            # Preserve up to 32 bits: requesting a fixed 16 bits would quantize
            # 24-bit FLAC sources. Let the native decoder choose its PCM depth.
            checked(invoke(reader, 7, HR, (DWORD, PTR, PTR), audio_stream, None, media_type), '选择 FLAC 解码输出')
            checked(invoke(reader, 6, HR, (DWORD, C.POINTER(PTR)), audio_stream, C.byref(actual_type)), '读取 PCM 类型')
            format_size = DWORD()
            checked(self._platform.MFCreateWaveFormatExFromMFMediaType(
                actual_type, C.byref(format_pointer), C.byref(format_size), 0), '读取 PCM 格式')
            fmt = C.cast(format_pointer, C.POINTER(WaveFormat)).contents
            if fmt.tag not in (1, 0xfffe) or fmt.bits not in (8, 16, 24, 32):
                raise RuntimeError('Windows 原生音频：FLAC 解码器没有返回整数 PCM。')
            with source.open('rb') as original:
                if original.read(4) == b'fLaC':
                    original.seek(18)
                    source_bits = ((int.from_bytes(original.read(8), 'big') >> 36) & 31)+1
                    if fmt.bits < source_bits:
                        raise RuntimeError('Windows 原生音频：系统解码器的 PCM 位深低于原始 FLAC。')
            frames = 0
            deadline = time.monotonic()+max(30., self.timeout)
            with wave.open(str(target), 'wb') as output:
                output.setnchannels(fmt.channels)
                output.setsampwidth(fmt.bits//8)
                output.setframerate(fmt.rate)
                while True:
                    if time.monotonic() > deadline:
                        raise RuntimeError('Windows 原生音频：FLAC 解码超时。')
                    sample, buffer = PTR(), PTR()
                    locked = False
                    try:
                        stream, flags, stamp = DWORD(), DWORD(), C.c_int64()
                        checked(invoke(reader, 9, HR,
                                       (DWORD, DWORD, C.POINTER(DWORD), C.POINTER(DWORD),
                                        C.POINTER(C.c_int64), C.POINTER(PTR)),
                                       audio_stream, 0, C.byref(stream), C.byref(flags), C.byref(stamp), C.byref(sample)),
                                '解码 FLAC')
                        if flags.value & (1 | 0x20):  # error / changed output type
                            raise RuntimeError('Windows 原生音频：FLAC 解码中断或格式改变。')
                        if sample:
                            checked(invoke(sample, 41, HR, (C.POINTER(PTR),), C.byref(buffer)), '读取 PCM 样本')
                            data, maximum, length = PTR(), DWORD(), DWORD()
                            checked(invoke(buffer, 3, HR, (C.POINTER(PTR), C.POINTER(DWORD), C.POINTER(DWORD)),
                                           C.byref(data), C.byref(maximum), C.byref(length)), '锁定 PCM 缓冲')
                            locked = True
                            if length.value % fmt.alignment:
                                raise RuntimeError('Windows 原生音频：PCM 样本未对齐。')
                            output.writeframesraw(C.string_at(data, length.value))
                            frames += length.value//fmt.alignment
                        if flags.value & 2:  # end of stream, after any final sample
                            break
                    finally:
                        if locked:
                            invoke(buffer, 4, HR)
                        release(buffer)
                        release(sample)
            if abs(frames/fmt.rate-self._precise_duration) > 1/fmt.rate:
                raise RuntimeError('Windows 原生音频：FLAC 解码样本数与原文件时长不匹配。')
            return target
        finally:
            if format_pointer:
                self._ole.CoTaskMemFree(format_pointer)
            release(actual_type)
            release(media_type)
            release(reader)

    def _check(self):
        if threading.get_ident() != self._owner:
            raise RuntimeError('Windows 原生后端必须在创建它的线程中使用和关闭。')
        if self._closed:
            raise RuntimeError('Windows 原生音频后端已关闭。')
        if self._notify:
            for kind, first, second in self._notify.drain():
                if kind == 5:
                    self._failure = f'媒体错误 {first} (HRESULT 0x{second:08X})'
                elif kind == 17:
                    self._seeked += 1
                elif kind in (12, 1005):
                    self._state.buffering = True
                elif kind in (13, 14, 15, 1006):
                    self._state.buffering = False
        if self._failure:
            raise RuntimeError(f'Windows 原生音频：{self._failure}；请检查媒体格式或音频设备。')

    def _value(self, slot, result):
        return invoke(self._engine, slot, result)

    def _command(self, slot, operation, signature=(), *values):
        self._check()
        checked(invoke(self._engine, slot, HR, signature, *values), operation)

    def _wait(self, condition, operation):
        deadline = time.monotonic() + self.timeout
        while True:
            self._check()
            if condition():
                return
            if time.monotonic() >= deadline:
                raise RuntimeError(f'Windows 原生音频：{operation} 超时。')
            time.sleep(.005)

    def poll(self):
        self._check()
        duration = self._precise_duration or self._value(19, DOUBLE)
        position = self._value(16, DOUBLE)
        if not math.isfinite(duration) or not math.isfinite(position):
            raise RuntimeError('Windows 原生音频：媒体时间无效。')
        ended = bool(self._value(27, BOOL))
        now = time.monotonic()
        self._state = replace(self._state, duration=duration, backend_position=position,
                              position=duration if ended else position,
                              paused=ended or bool(self._value(20, BOOL)), seeking=bool(self._value(15, BOOL)),
                              ended=ended, volume=self._value(36, DOUBLE),
                              updated_at=now, connected_at=now)
        return replace(self._state)

    def play(self):
        if self.poll().ended:
            self.seek(0.)
        self._command(32, '播放')

    def pause(self):
        self._command(33, '暂停')
        # Pause updates IsPaused before the presentation clock has stopped.
        position = self._value(16, DOUBLE)
        stable_since = time.monotonic()
        def stopped():
            nonlocal position, stable_since
            current = self._value(16, DOUBLE)
            paused = bool(self._value(20, BOOL))
            if current != position or not paused:
                position, stable_since = current, time.monotonic()
            return paused and time.monotonic()-stable_since >= .05
        self._wait(stopped, '暂停时钟')

    def seek(self, target):
        if not math.isfinite(target):
            raise ValueError('跳转时间必须是有限数值。')
        state = self.poll()
        target = min(state.duration, max(0., target))
        started = time.monotonic()
        self.last_seek_target = target
        if abs(state.position-target) > .00001:
            prior = self._seeked
            self._command(17, '跳转', (DOUBLE,), target)
            self._wait(lambda: self._seeked > prior and not self._value(15, BOOL), '跳转')
        self.last_seek_seconds = time.monotonic()-started
        self.poll()

    def set_volume(self, value):
        if not math.isfinite(value):
            raise ValueError('音量必须是有限数值。')
        self._command(37, '设置音量', (DOUBLE,), min(1., max(0., value)))

    def close(self):
        if self._closed:
            return
        if threading.get_ident() != self._owner:
            raise RuntimeError('Windows 原生后端必须在创建它的线程中关闭。')
        self._closed = True
        errors = []
        try:
            if self._engine:
                try:
                    checked(invoke(self._engine, 42, HR), '关闭引擎')
                except Exception as exc:
                    errors.append(str(exc))
                finally:
                    release(self._engine)
        finally:
            release(self._attributes)
            release(self._factory)
            if self._mf:
                hr = self._platform.MFShutdown()
                self._mf = False
                if hr < 0:
                    errors.append(f'MFShutdown: 0x{hr & 0xffffffff:08X}')
            if self._com:
                self._ole.CoUninitialize()
                self._com = False
            if self._scratch:
                self._scratch.cleanup()
                self._scratch = None
        if errors:
            raise RuntimeError('; '.join(errors))
