import unittest

import cv2

from nte_ocr.rules import decide, parse_affix
from nte_ocr.vision import Reader, Scene, fast_forward_template, find_fast_forward, find_panel, marker_active, selected_item
from tests.fixtures_support import screenshot_fixtures

FIXTURES = None


class ScreenshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        global FIXTURES
        FIXTURES = screenshot_fixtures()
        cls.reader = Reader()

    def test_real_result_pages(self):
        expected = {
            'result_a': (0, ['攻击力固定值', '伤害增加', '攻击力百分比', '防御力固定值'], False, False),
            'result_b': (5, ['暴击伤害', '防御力百分比', '攻击力百分比', '生命值百分比'], False, True),
        }
        for name, (selection, names, keep, discarded) in expected.items():
            with self.subTest(name=name):
                image = cv2.imread(str(FIXTURES / f'{name}.png'))
                panel = find_panel(image)
                self.assertIsNotNone(panel)
                self.assertTrue(self.reader.is_result(image))
                self.assertEqual(selected_item(image, panel), selection)
                affixes = self.reader.affixes(image, panel)
                self.assertEqual([a.name for a in affixes], names)
                self.assertEqual(decide(affixes).keep, keep)
                self.assertFalse(marker_active(image, panel, True))
                self.assertEqual(marker_active(image, panel, False), discarded)

    def test_enlarged_examples_match_user_rule(self):
        for name, expected in [('detail_a', True), ('detail_b', False), ('detail_tilt', False)]:
            with self.subTest(name=name):
                image = cv2.imread(str(FIXTURES / f'{name}.png'))
                texts = self.reader.texts(image)
                affixes = [a for t in sorted(texts, key=lambda t: t.y)
                           if t.score >= .88 and (a := parse_affix(t.text))]
                self.assertEqual(len(affixes), 4)
                self.assertEqual(decide(affixes).keep, expected)

    def test_menu_and_animation_are_not_results(self):
        menu = cv2.imread(str(FIXTURES / 'menu.png'))
        animation = cv2.imread(str(FIXTURES / 'animation.png'))
        for image in (menu, animation):
            self.assertIsNone(find_panel(image))
            self.assertFalse(self.reader.is_result(image))
        self.assertIsNotNone(self.reader.coin_button(menu))
        self.assertIsNotNone(find_fast_forward(animation))
        for width in (800, 1280, 1920):
            scaled = cv2.resize(animation, (width, round(animation.shape[0]*width/animation.shape[1])))
            self.assertIsNotNone(find_fast_forward(scaled), f'快进模板未匹配宽度 {width}')
        self.assertIsNone(find_fast_forward(menu))

    def test_users_current_advanced_coin_page(self):
        image = cv2.imread(str(FIXTURES / 'menu_live.png'))
        point = self.reader.coin_button(image)
        self.assertIsNotNone(point)
        self.assertTrue(850 < point[0] < 1000)
        self.assertTrue(550 < point[1] < 630)
        self.assertIsNone(find_panel(image))

    def test_all_cycle_screens_are_classified(self):
        for name, expected in [('menu', Scene.MENU), ('animation', Scene.ANIMATION),
                               ('result_a', Scene.RESULT), ('result_b', Scene.RESULT)]:
            with self.subTest(name=name):
                image = cv2.imread(str(FIXTURES / f'{name}.png'))
                self.assertEqual(self.reader.scene(image).scene, expected)

    def test_result_panel_takes_priority_over_lingering_skip_icon(self):
        image = cv2.imread(str(FIXTURES / 'result_a.png'))
        icon = cv2.cvtColor(fast_forward_template(), cv2.COLOR_GRAY2BGR)
        image[14:14+icon.shape[0], 935:935+icon.shape[1]] = icon
        self.assertIsNotNone(find_fast_forward(image))
        self.assertEqual(self.reader.scene(image).scene, Scene.RESULT)

    def test_resized_result(self):
        original = cv2.imread(str(FIXTURES / 'result_a.png'))
        for width in (800, 1280, 1920):
            with self.subTest(width=width):
                image = cv2.resize(original, (width, round(original.shape[0]*width/original.shape[1])))
                panel = find_panel(image)
                self.assertIsNotNone(panel)
                self.assertEqual(selected_item(image, panel), 0)
                self.assertEqual([a.name for a in self.reader.affixes(image, panel)],
                                 ['攻击力固定值', '伤害增加', '攻击力百分比', '防御力固定值'])
