"""窗口枚举、WGC 截图及后台消息点击，不移动系统鼠标。"""
import ctypes as ct
from ctypes import wintypes as wt
from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from .capture import WindowCaptureSession, crop_client
from .paths import application_directory


user32 = ct.WinDLL('user32', use_last_error=True)
kernel32 = ct.WinDLL('kernel32', use_last_error=True)
advapi32 = ct.WinDLL('advapi32', use_last_error=True)
shell32 = ct.WinDLL('shell32', use_last_error=True)
dwmapi = ct.WinDLL('dwmapi', use_last_error=True)
user32.SetProcessDpiAwarenessContext.argtypes = [wt.HANDLE]
user32.SetProcessDpiAwarenessContext(ct.c_void_p(-4))
WNDENUMPROC = ct.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wt.LPARAM]
user32.IsWindowVisible.argtypes = [wt.HWND]
user32.IsWindow.argtypes = [wt.HWND]
user32.IsIconic.argtypes = [wt.HWND]
user32.GetWindowTextLengthW.argtypes = [wt.HWND]
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ct.c_int]
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ct.POINTER(wt.DWORD)]
user32.GetClientRect.argtypes = [wt.HWND, ct.POINTER(wt.RECT)]
user32.ClientToScreen.argtypes = [wt.HWND, ct.POINTER(wt.POINT)]
user32.GetAsyncKeyState.argtypes = [ct.c_int]
user32.GetAsyncKeyState.restype = ct.c_short
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.GetCursorPos.argtypes = [ct.POINTER(wt.POINT)]
user32.GetWindowRect.argtypes = [wt.HWND, ct.POINTER(wt.RECT)]
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ct.c_int, ct.c_int, ct.c_int, ct.c_int, wt.UINT]
user32.SendMessageTimeoutW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM, wt.UINT,
                                      wt.UINT, ct.POINTER(ct.c_size_t)]
user32.SendMessageTimeoutW.restype = ct.c_ssize_t
dwmapi.DwmGetWindowAttribute.argtypes = [wt.HWND, wt.DWORD, ct.c_void_p, wt.DWORD]
kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.OpenProcess.restype = wt.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wt.HANDLE, wt.DWORD, wt.LPWSTR, ct.POINTER(wt.DWORD)]
kernel32.CloseHandle.argtypes = [wt.HANDLE]
advapi32.OpenProcessToken.argtypes = [wt.HANDLE, wt.DWORD, ct.POINTER(wt.HANDLE)]
advapi32.GetTokenInformation.argtypes = [wt.HANDLE, ct.c_int, ct.c_void_p, wt.DWORD, ct.POINTER(wt.DWORD)]
shell32.ShellExecuteW.argtypes = [wt.HWND, wt.LPCWSTR, wt.LPCWSTR, wt.LPCWSTR, wt.LPCWSTR, ct.c_int]
shell32.ShellExecuteW.restype = ct.c_ssize_t


class WindowError(RuntimeError):
    pass


def api_error(operation: str) -> WindowError:
    code = ct.get_last_error()
    detail = ct.FormatError(code).strip() if code else 'Windows 未提供错误码'
    return WindowError(f'{operation} 失败：{detail}（错误码 {code}）')


def process_elevated(pid: int) -> bool:
    process = kernel32.OpenProcess(0x1000, False, pid)
    if not process:
        raise api_error('查询进程权限 / OpenProcess')
    try:
        token = wt.HANDLE()
        if not advapi32.OpenProcessToken(process, 8, ct.byref(token)):
            raise api_error('查询进程权限 / OpenProcessToken')
        try:
            elevated, size = wt.DWORD(), wt.DWORD()
            if not advapi32.GetTokenInformation(token, 20, ct.byref(elevated),
                                                ct.sizeof(elevated), ct.byref(size)):
                raise api_error('查询进程权限 / GetTokenInformation')
            return bool(elevated.value)
        finally:
            kernel32.CloseHandle(token)
    finally:
        kernel32.CloseHandle(process)


def restart_elevated(*, start: bool):
    root = application_directory()
    args = [] if getattr(sys, 'frozen', False) else [str(root / 'main.py')]
    if start:
        args.append('--start')
    ct.set_last_error(0)
    result = shell32.ShellExecuteW(None, 'runas', sys.executable,
                                  subprocess.list2cmdline(args), str(root), 1)
    if result <= 32:
        code = ct.get_last_error()
        if code == 1223:
            raise WindowError('管理员授权已取消；游戏使用管理员权限，工具需要相同权限才能点击')
        raise api_error('请求管理员权限')


@dataclass
class GameWindow:
    hwnd: int
    title: str
    process: str
    session: WindowCaptureSession | None = field(default=None, init=False, repr=False, compare=False)

    @property
    def label(self):
        return f'{self.title}  [{self.process}]'

    def needs_elevation(self) -> bool:
        pid = wt.DWORD()
        if not user32.GetWindowThreadProcessId(self.hwnd, ct.byref(pid)):
            raise api_error('查询游戏进程 / GetWindowThreadProcessId')
        return process_elevated(pid.value) and not process_elevated(os.getpid())

    def check_input_permission(self):
        if self.needs_elevation():
            raise WindowError('游戏正在以管理员身份运行，工具权限不足；请重新开始并允许管理员权限重启')

    def rect(self) -> dict:
        if not user32.IsWindow(self.hwnd) or user32.IsIconic(self.hwnd):
            raise WindowError('游戏窗口已关闭或最小化')
        rect, origin = wt.RECT(), wt.POINT(0, 0)
        if not user32.GetClientRect(self.hwnd, ct.byref(rect)):
            raise api_error('读取游戏尺寸 / GetClientRect')
        if not user32.ClientToScreen(self.hwnd, ct.byref(origin)):
            raise api_error('转换游戏坐标 / ClientToScreen')
        if rect.right < 640 or rect.bottom < 360:
            raise WindowError('游戏客户区太小，请至少使用 640×360')
        return dict(left=origin.x, top=origin.y, width=rect.right, height=rect.bottom)

    def start_capture(self):
        self.rect()
        self.session = WindowCaptureSession(self.hwnd)

    def close_capture(self):
        if self.session is not None:
            self.session.close()
            self.session = None

    def capture(self):
        rect = self.rect()
        frame = self.session.read()
        bounds = wt.RECT()
        result = dwmapi.DwmGetWindowAttribute(self.hwnd, 9, ct.byref(bounds), ct.sizeof(bounds))
        if result != 0:
            raise WindowError(f'读取窗口边界失败 / DwmGetWindowAttribute（HRESULT {result}）')
        if self.rect() != rect:
            raise WindowError('截图过程中游戏窗口发生移动或缩放，请重新开始')
        return crop_client(frame, rect, (bounds.left, bounds.top, bounds.right, bounds.bottom)), rect

    def send_message(self, message, buttons, position):
        result = ct.c_size_t()
        ct.set_last_error(0)
        if not user32.SendMessageTimeoutW(self.hwnd, message, buttons, position, 2, 300, ct.byref(result)):
            raise api_error(f'窗口模拟点击 / SendMessageTimeoutW（消息 {message:#x}）')

    def click(self, point, expected_rect):
        self.check_input_permission()
        rect = self.rect()
        if rect != expected_rect:
            raise WindowError('游戏窗口位置或尺寸改变，已停止，请重新开始')
        x, y = point
        if not (0 <= x < rect['width'] and 0 <= y < rect['height']):
            raise WindowError('识别到的操作位置超出游戏客户区')
        position = (y << 16) | x
        self.send_message(0x0006, 1, 0)
        self.send_message(0x0200, 1, position)
        time.sleep(.01)
        try:
            self.send_message(0x0201, 1, position)
            time.sleep(.04)
        finally:
            self.send_message(0x0202, 0, position)

    def click_aligned(self, point, expected_rect):
        """临时移位窗口对齐真实光标，模拟点击后立即还原，不移动光标。"""
        self.check_input_permission()
        rect = self.rect()
        if rect != expected_rect:
            raise WindowError('游戏窗口位置或尺寸改变，已停止，请重新开始')
        x, y = point
        if not (0 <= x < rect['width'] and 0 <= y < rect['height']):
            raise WindowError('识别到的操作位置超出游戏客户区')
        cursor, original = wt.POINT(), wt.RECT()
        if not user32.GetCursorPos(ct.byref(cursor)):
            raise api_error('读取光标位置 / GetCursorPos')
        if not user32.GetWindowRect(self.hwnd, ct.byref(original)):
            raise api_error('读取窗口位置 / GetWindowRect')

        self.send_message(0x0006, 1, 0)
        left = original.left + cursor.x - (rect['left'] + x)
        top = original.top + cursor.y - (rect['top'] + y)
        # NOSIZE | NOZORDER | NOACTIVATE：只平移，不改变尺寸、层级或前台窗口。
        if not user32.SetWindowPos(self.hwnd, None, left, top, 0, 0, 0x0015):
            raise api_error('对齐窗口位置 / SetWindowPos')
        try:
            position = (y << 16) | x
            self.send_message(0x0200, 1, position)
            time.sleep(.02)
            try:
                self.send_message(0x0201, 1, position)
                time.sleep(.05)
            finally:
                self.send_message(0x0202, 0, position)
            time.sleep(.03)
        finally:
            if not user32.SetWindowPos(self.hwnd, None, original.left, original.top, 0, 0, 0x0015):
                raise api_error('还原窗口位置 / SetWindowPos')


def list_windows() -> list[GameWindow]:
    windows = []

    @WNDENUMPROC
    def visit(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if not length:
            return True
        title = ct.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title, length + 1)
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ct.byref(pid))
        if pid.value == os.getpid():
            return True
        handle = kernel32.OpenProcess(0x1000, False, pid.value)
        process = ''
        if handle:
            try:
                path, size = ct.create_unicode_buffer(32768), wt.DWORD(32768)
                if kernel32.QueryFullProcessImageNameW(handle, 0, path, ct.byref(size)):
                    process = Path(path.value).name
            finally:
                kernel32.CloseHandle(handle)
        windows.append(GameWindow(hwnd, title.value, process))
        return True

    if not user32.EnumWindows(visit, 0):
        raise ct.WinError(ct.get_last_error())
    return windows


def is_game(window: GameWindow) -> bool:
    return bool(re.fullmatch(r'(?:HTGame|NTE(?:[-_]Win64[-_]Shipping)?|NevernessToEverness)\.exe',
                             window.process, re.IGNORECASE)
                or window.title.strip() in ('异环', 'NTE', 'Neverness to Everness'))


def key_down(vk: int) -> bool:
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)
