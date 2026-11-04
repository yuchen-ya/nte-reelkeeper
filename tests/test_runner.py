from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

import cv2
import numpy as np

from nte_ocr.runner import Options, Runner, Stopped
from nte_ocr.vision import Reader, RecognitionError, find_panel
from tests.fixtures_support import screenshot_fixtures

FIXTURES = None


class ReplayWindow:
    """回放实际截图，记录点击并显示其选中/打标结果，不操作真实游戏。"""
    def __init__(self):
        self.page = 'menu'
        self.index = 0
        self.marked = [False] * 10
        self.coin_clicks = 0
        self.mark_clicks = 0
        self.ignore_selection = False
        self.menu = cv2.imread(str(FIXTURES / 'menu.png'))
        self.animation = cv2.imread(str(FIXTURES / 'animation.png'))
        self.result = cv2.imread(str(FIXTURES / 'result_a.png'))
        self.panel = find_panel(self.result)
        hsv = cv2.cvtColor(self.result, cv2.COLOR_BGR2HSV)
        pink = cv2.inRange(hsv, np.array((145, 150, 150)), np.array((179, 255, 255)))
        self.result = cv2.inpaint(self.result, pink, 3, cv2.INPAINT_TELEA)
        self.rect = dict(left=0, top=0, width=self.result.shape[1], height=self.result.shape[0])

    def capture(self):
        if self.page == 'menu':
            return self.menu.copy(), self.rect
        if self.page == 'animation':
            return self.animation.copy(), self.rect
        image = self.result.copy()
        x, y = self.panel.item_point(self.index)
        radius = round(self.panel.width * .20)
        cv2.rectangle(image, (x-radius, y-radius), (x+radius, y+radius), (144, 45, 240), 5)
        if self.marked[self.index]:
            cv2.circle(image, self.panel.discard_point, 4, (240, 240, 240), -1)
        return image, self.rect

    def click(self, point, rect):
        if self.page == 'menu':
            self.coin_clicks += 1
            self.marked = [False] * 10
            self.page = 'animation'
        elif self.page == 'animation':
            self.page = 'result'
        elif np.linalg.norm(np.array(point) - self.panel.discard_point) < 8:
            self.marked[self.index] = not self.marked[self.index]
            self.mark_clicks += 1
        elif point[1] > self.rect['height'] * .85:
            self.page = 'menu'
        elif not self.ignore_selection:
            self.index = min(range(10), key=lambda i: np.linalg.norm(np.array(point)-self.panel.item_point(i)))

    def click_aligned(self, point, rect):
        self.click(point, rect)


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global FIXTURES
        FIXTURES = screenshot_fixtures()
        cls.reader = Reader()

    def runner(self, window, options, event=None):
        runner = Runner(window, self.reader, options, event or threading.Event(), lambda *_: None)
        return runner

    def test_from_coin_page_through_two_rounds(self):
        with tempfile.TemporaryDirectory() as folder, patch('nte_ocr.runner.ROOT', Path(folder)):
            # 实际 OCR 与页面识别保持启用，点击只发送给回放窗口。
            window = ReplayWindow()
            runner = self.runner(window, Options(rounds=2))
            runner.run()
            self.assertEqual(window.coin_clicks, 2)
            self.assertEqual(window.mark_clicks, 20)
            self.assertEqual(window.page, 'menu')
            self.assertEqual(len(runner.log_path.read_text(encoding='utf-8').splitlines()), 20)

    def test_delayed_animation_frame_does_not_close_second_round_results(self):
        class DelayedFrameWindow(ReplayWindow):
            def __init__(self):
                super().__init__()
                self.stale_frames = 0
                self.skip_clicks = 0

            def capture(self):
                if self.stale_frames:
                    self.stale_frames -= 1
                    return self.animation.copy(), self.rect
                return super().capture()

            def click_aligned(self, point, rect):
                if self.page == 'animation':
                    self.skip_clicks += 1
                    super().click_aligned(point, rect)
                    self.stale_frames = 1
                elif self.page == 'result' and point[0] > self.rect['width'] * .9:
                    self.skip_clicks += 1
                    self.page = 'menu'
                else:
                    super().click_aligned(point, rect)

        with tempfile.TemporaryDirectory() as folder, patch('nte_ocr.runner.ROOT', Path(folder)):
            window = DelayedFrameWindow()
            runner = self.runner(window, Options(rounds=2))
            runner.run()
            self.assertEqual(window.skip_clicks, 2)
            self.assertEqual(window.coin_clicks, 2)
            self.assertEqual(window.mark_clicks, 20)
            self.assertEqual(window.page, 'menu')

    def test_resume_animation_or_partial_results_without_another_coin(self):
        for page in ('animation', 'result'):
            with self.subTest(page=page), tempfile.TemporaryDirectory() as folder, \
                    patch('nte_ocr.runner.ROOT', Path(folder)):
                window = ReplayWindow()
                window.page, window.index = page, 6
                window.marked[:3] = [True] * 3
                runner = self.runner(window, Options())
                runner.run()
                self.assertEqual(window.coin_clicks, 0)
                self.assertEqual(window.mark_clicks, 7)
                self.assertTrue(all(window.marked))

    def test_coin_click_targets_the_ten_pull_button(self):
        with tempfile.TemporaryDirectory() as folder, patch('nte_ocr.runner.ROOT', Path(folder)):
            window = ReplayWindow()
            runner = self.runner(window, Options())
            with patch.object(window, 'click', wraps=window.click) as click:
                runner.run()
                x, y = click.call_args_list[0].args[0]
                self.assertTrue(650 < x < 730)
                self.assertTrue(440 < y < 480)

    def test_unresponsive_coin_button_is_not_clicked_repeatedly(self):
        with tempfile.TemporaryDirectory() as folder, patch('nte_ocr.runner.ROOT', Path(folder)):
            window = ReplayWindow()
            runner = self.runner(window, Options())
            with patch.object(window, 'click_aligned') as click, \
                    patch('nte_ocr.runner.time.monotonic', side_effect=[0, 1, 2, 3, 8]):
                with self.assertRaisesRegex(RecognitionError, '未响应后台投币'):
                    runner.reach_result()
                self.assertEqual(click.call_count, 1)
                self.assertTrue(runner.log_path.with_suffix('.failure.png').is_file())

    def test_resume_transition_before_animation(self):
        with tempfile.TemporaryDirectory() as folder, patch('nte_ocr.runner.ROOT', Path(folder)):
            window = ReplayWindow()
            window.page = 'animation'
            original_capture = window.capture
            captures = 0
            def capture():
                nonlocal captures
                captures += 1
                if captures <= 2:
                    return np.zeros_like(window.animation), window.rect
                return original_capture()
            with patch.object(window, 'capture', side_effect=capture):
                self.runner(window, Options()).run()
            self.assertEqual(window.coin_clicks, 0)
            self.assertEqual(window.mark_clicks, 10)

    def test_existing_mark_is_not_toggled_off(self):
        with tempfile.TemporaryDirectory() as folder, patch('nte_ocr.runner.ROOT', Path(folder)):
            window = ReplayWindow()
            window.page, window.marked = 'result', [True] * 10
            self.runner(window, Options(mode='current')).run()
            self.assertEqual(window.mark_clicks, 0)
            self.assertTrue(all(window.marked))

    def test_preview_and_selection_failure_do_not_mark(self):
        with tempfile.TemporaryDirectory() as folder, patch('nte_ocr.runner.ROOT', Path(folder)):
            window = ReplayWindow()
            window.page = 'result'
            self.runner(window, Options(mode='current', dry_run=True)).run()
            self.assertEqual(window.mark_clicks, 0)
            window.page, window.index, window.ignore_selection = 'result', 4, True
            with self.assertRaises(RecognitionError):
                self.runner(window, Options(mode='current')).run()
            self.assertEqual(window.mark_clicks, 0)

    def test_stop_before_first_click(self):
        with tempfile.TemporaryDirectory() as folder, patch('nte_ocr.runner.ROOT', Path(folder)):
            window, event = ReplayWindow(), threading.Event()
            event.set()
            with self.assertRaises(Stopped):
                self.runner(window, Options(), event).run()
            self.assertEqual(window.coin_clicks, 0)
