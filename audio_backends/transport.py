"""Bounded JSON IPC transport: Windows overlapped pipes or POSIX sockets."""
import os
import socket


class UnixSocket:
    def __init__(self, address):
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self.socket.connect(address)
        except BaseException:
            self.socket.close()
            raise

    def send(self, data, timeout):
        self.socket.settimeout(timeout)
        self.socket.sendall(data)

    def receive(self, timeout):
        self.socket.settimeout(timeout)
        try:
            data = self.socket.recv(65536)
        except socket.timeout as exc:
            raise TimeoutError('mpv IPC 读取超时') from exc
        if not data:
            raise ConnectionError('mpv IPC 已断开')
        return data

    def close(self):
        self.socket.close()


class WindowsPipe:
    def __init__(self, address):
        import ctypes
        from ctypes import wintypes
        self.ctypes = ctypes
        self.wintypes = wintypes

        class Overlapped(ctypes.Structure):
            _fields_ = [('Internal', ctypes.c_size_t), ('InternalHigh', ctypes.c_size_t),
                        ('Offset', wintypes.DWORD), ('OffsetHigh', wintypes.DWORD),
                        ('hEvent', wintypes.HANDLE)]

        self.Overlapped = Overlapped
        api = self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        api.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                   ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        api.CreateFileW.restype = wintypes.HANDLE
        api.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
        api.CreateEventW.restype = wintypes.HANDLE
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        api.CloseHandle.restype = wintypes.BOOL
        api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        api.WaitForSingleObject.restype = wintypes.DWORD
        for name in ('ReadFile', 'WriteFile'):
            fn = getattr(api, name)
            fn.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                           ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(Overlapped)]
            fn.restype = wintypes.BOOL
        api.GetOverlappedResult.argtypes = [wintypes.HANDLE, ctypes.POINTER(Overlapped),
                                           ctypes.POINTER(wintypes.DWORD), wintypes.BOOL]
        api.GetOverlappedResult.restype = wintypes.BOOL
        api.CancelIoEx.argtypes = [wintypes.HANDLE, ctypes.POINTER(Overlapped)]
        api.CancelIoEx.restype = wintypes.BOOL
        self.handle = api.CreateFileW(address, 0xC0000000, 0, None, 3, 0x40000000, None)
        if self.handle == ctypes.c_void_p(-1).value:
            self.handle = None
            raise ctypes.WinError(ctypes.get_last_error())

    def _transfer(self, data, timeout, reading):
        ctypes, api = self.ctypes, self.api
        if self.handle is None:
            raise ConnectionError('mpv IPC 已关闭')
        buffer = ctypes.create_string_buffer(65536) if reading else ctypes.create_string_buffer(data)
        count = self.wintypes.DWORD()
        operation = self.Overlapped()
        operation.hEvent = api.CreateEventW(None, True, False, None)
        if not operation.hEvent:
            raise ctypes.WinError(ctypes.get_last_error())
        pending = False
        try:
            fn = api.ReadFile if reading else api.WriteFile
            ok = fn(self.handle, buffer, 65536 if reading else len(data),
                    ctypes.byref(count), ctypes.byref(operation))
            if not ok:
                error = ctypes.get_last_error()
                if error != 997:  # ERROR_IO_PENDING
                    raise ctypes.WinError(error)
                pending = True
                result = api.WaitForSingleObject(operation.hEvent, max(1, int(timeout * 1000)))
                if result == 258:  # WAIT_TIMEOUT
                    raise TimeoutError('mpv IPC 通信超时')
                if result != 0:
                    raise ctypes.WinError(ctypes.get_last_error())
                if not api.GetOverlappedResult(self.handle, ctypes.byref(operation), ctypes.byref(count), False):
                    raise ctypes.WinError(ctypes.get_last_error())
                pending = False
            if reading:
                if not count.value:
                    raise ConnectionError('mpv IPC 已断开')
                return buffer.raw[:count.value]
            if count.value != len(data):
                raise ConnectionError('mpv IPC 写入不完整')
        finally:
            if pending:
                # The OVERLAPPED and buffer must stay alive until cancellation completes.
                api.CancelIoEx(self.handle, ctypes.byref(operation))
                api.GetOverlappedResult(self.handle, ctypes.byref(operation), ctypes.byref(count), True)
            api.CloseHandle(operation.hEvent)

    def send(self, data, timeout):
        self._transfer(data, timeout, False)

    def receive(self, timeout):
        return self._transfer(None, timeout, True)

    def close(self):
        if self.handle is not None:
            self.api.CloseHandle(self.handle)
            self.handle = None


def connect(address):
    return WindowsPipe(address) if os.name == 'nt' else UnixSocket(address)
