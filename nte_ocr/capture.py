"""通过 Windows Graphics Capture 获取指定 HWND 的画面。"""
import threading

import numpy as np
from windows_capture import WindowsCapture


class WindowCaptureSession:
    def __init__(self, hwnd: int):
        self.condition = threading.Condition()
        self.image = None
        self.version = 0
        self.closed = False
        self.capture = WindowsCapture(window_hwnd=hwnd, cursor_capture=False,
                                      draw_border=False, minimum_update_interval=16)

        @self.capture.event
        def on_frame_arrived(frame, _):
            with self.condition:
                self.image = frame.frame_buffer[:, :, :3].copy()
                self.version += 1
                self.condition.notify_all()

        @self.capture.event
        def on_closed():
            with self.condition:
                self.closed = True
                self.condition.notify_all()

        self.control = self.capture.start_free_threaded()

    def read(self) -> np.ndarray:
        with self.condition:
            version = self.version
            ready = self.condition.wait_for(lambda: self.version > version or self.closed, timeout=3)
            if self.closed:
                raise OSError('游戏窗口后台截图已关闭，请重新开始')
            if not ready:
                raise OSError('等待后台画面超时，请保持游戏未最小化并允许后台渲染')
            return self.image.copy()

    def close(self):
        self.control.stop()


def crop_client(image: np.ndarray, client: dict, bounds: tuple[int, int, int, int]) -> np.ndarray:
    height, width = image.shape[:2]
    if (width, height) == (client['width'], client['height']):
        return image
    left, top, right, bottom = bounds
    if (right-left, bottom-top) != (width, height):
        raise OSError('后台截图尺寸与窗口不一致，请重新开始')
    x, y = client['left']-left, client['top']-top
    if x < 0 or y < 0 or x+client['width'] > width or y+client['height'] > height:
        raise OSError('后台截图的客户区超出窗口范围')
    return image[y:y+client['height'], x:x+client['width']].copy()
