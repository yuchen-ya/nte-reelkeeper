import ctypes as ct
from ctypes import wintypes as wt
import unittest
from unittest.mock import MagicMock, call, patch

from nte_ocr.windows import GameWindow, WindowError, restart_elevated


class InputTests(unittest.TestCase):
    def setUp(self):
        self.window = GameWindow(42, '异环', 'HTGame.exe')
        self.rect = dict(left=100, top=200, width=1280, height=720)
        # 此边界只允许后台消息；若恢复移动鼠标或抢焦点会直接失败。
        self.api = MagicMock(spec=['PostMessageW', 'GetCursorPos', 'GetWindowRect',
                                   'SetWindowPos', 'SendMessageTimeoutW'])
        self.api.PostMessageW.return_value = 1
        self.api.SetWindowPos.return_value = 1
        self.api.SendMessageTimeoutW.return_value = 1

        def cursor(pointer):
            value = ct.cast(pointer, ct.POINTER(wt.POINT)).contents
            value.x, value.y = 900, 800
            return 1

        def window_rect(_, pointer):
            value = ct.cast(pointer, ct.POINTER(wt.RECT)).contents
            value.left, value.top, value.right, value.bottom = 90, 170, 1390, 920
            return 1

        self.api.GetCursorPos.side_effect = cursor
        self.api.GetWindowRect.side_effect = window_rect
        self.api_patch = patch('nte_ocr.windows.user32', self.api)
        self.api_patch.start()
        self.addCleanup(self.api_patch.stop)
        self.rect_patch = patch.object(GameWindow, 'rect', return_value=self.rect)
        self.rect_patch.start()
        self.addCleanup(self.rect_patch.stop)
        self.permission_patch = patch.object(GameWindow, 'needs_elevation', return_value=False)
        self.needs_elevation = self.permission_patch.start()
        self.addCleanup(self.permission_patch.stop)
        sleep_patch = patch('nte_ocr.windows.time.sleep')
        sleep_patch.start()
        self.addCleanup(sleep_patch.stop)

    def test_elevated_game_is_rejected_before_input(self):
        self.needs_elevation.return_value = True
        with self.assertRaisesRegex(WindowError, '管理员'):
            self.window.click((200, 300), self.rect)
        self.api.SendMessageTimeoutW.assert_not_called()

    def test_background_click_uses_client_coordinates_without_focus_or_cursor(self):
        self.window.click((200, 300), self.rect)
        position = (300 << 16) | 200
        messages = [c.args[:4] for c in self.api.SendMessageTimeoutW.call_args_list]
        self.assertEqual(messages, [(42, 0x0006, 1, 0), (42, 0x0200, 1, position),
                                    (42, 0x0201, 1, position), (42, 0x0202, 0, position)])

    def test_zero_error_never_claims_success(self):
        self.api.SendMessageTimeoutW.return_value = 0
        with self.assertRaisesRegex(WindowError, 'SendMessageTimeoutW.*未提供错误码'):
            self.window.click((200, 300), self.rect)
        self.assertEqual(self.api.SendMessageTimeoutW.call_count, 1)

    def test_changed_window_is_not_clicked(self):
        with self.assertRaisesRegex(WindowError, '位置或尺寸改变'):
            self.window.click((250, 300), {**self.rect, 'width': 1920})
        self.api.SendMessageTimeoutW.assert_not_called()

    def test_outside_client_area_is_not_clicked(self):
        with self.assertRaisesRegex(WindowError, '超出游戏客户区'):
            self.window.click((1280, 300), self.rect)
        self.api.SendMessageTimeoutW.assert_not_called()

    def test_aligned_click_moves_only_window_and_always_restores_it(self):
        self.window.click_aligned((200, 300), self.rect)
        self.assertEqual(self.api.SetWindowPos.call_args_list,
                         [call(42, None, 690, 470, 0, 0, 0x15),
                          call(42, None, 90, 170, 0, 0, 0x15)])

    def test_aligned_click_restores_window_when_mouse_message_fails(self):
        self.api.SendMessageTimeoutW.side_effect = [1, 1, 0, 1]
        with self.assertRaisesRegex(WindowError, 'SendMessageTimeoutW'):
            self.window.click_aligned((200, 300), self.rect)
        self.assertEqual(self.api.SetWindowPos.call_args_list[-1], call(42, None, 90, 170, 0, 0, 0x15))
        self.assertEqual(self.api.SendMessageTimeoutW.call_args_list[-1].args[1], 0x0202)


class ElevationTests(unittest.TestCase):
    def test_frozen_restart_uses_executable_without_python_script(self):
        with patch('nte_ocr.windows.shell32') as shell, patch('sys.frozen', True, create=True), \
                patch('sys.executable', 'C:/便携 程序/ReelKeeper.exe'):
            shell.ShellExecuteW.return_value = 42
            restart_elevated(start=True)
            args = shell.ShellExecuteW.call_args.args
            self.assertEqual(args[2], 'C:/便携 程序/ReelKeeper.exe')
            self.assertEqual(args[3], '--start')
            self.assertNotIn('main.py', args[3])

    def test_admin_game_requires_admin_tool(self):
        with patch('nte_ocr.windows.user32') as api, \
                patch('nte_ocr.windows.process_elevated', side_effect=[True, False]):
            api.GetWindowThreadProcessId.return_value = 1
            self.assertTrue(GameWindow(42, '异环', 'HTGame.exe').needs_elevation())

    def test_both_admin_permissions_match(self):
        with patch('nte_ocr.windows.user32') as api, \
                patch('nte_ocr.windows.process_elevated', side_effect=[True, True]):
            api.GetWindowThreadProcessId.return_value = 1
            self.assertFalse(GameWindow(42, '异环', 'HTGame.exe').needs_elevation())

    def test_restart_requests_runas_and_preserves_start(self):
        with patch('nte_ocr.windows.shell32') as shell:
            shell.ShellExecuteW.return_value = 42
            restart_elevated(start=True)
            args = shell.ShellExecuteW.call_args.args
            self.assertEqual(args[1], 'runas')
            self.assertIn('main.py', args[3])
            self.assertIn('--start', args[3])

    def test_cancelled_admin_prompt_does_not_report_success(self):
        with patch('nte_ocr.windows.shell32') as shell:
            def cancel(*_):
                ct.set_last_error(1223)
                return 5
            shell.ShellExecuteW.side_effect = cancel
            with self.assertRaisesRegex(WindowError, '授权已取消'):
                restart_elevated(start=True)
