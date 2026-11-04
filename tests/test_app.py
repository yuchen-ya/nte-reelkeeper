import json
from pathlib import Path
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch

from nte_ocr.app import App
from nte_ocr.rules import KeepRule, RetainCondition
from nte_ocr.runner import Options
from nte_ocr.ui_rules import RuleEditor


class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        for target, value in [('nte_ocr.app.ROOT', Path(self.folder.name)),
                              ('nte_ocr.app.list_windows', lambda: []),
                              ('nte_ocr.app.key_down', lambda _: False),
                              ('nte_ocr.app.App.preload_reader', lambda _: None)]:
            mock = patch(target, value)
            mock.start()
            self.addCleanup(mock.stop)
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.app = App(self.root)

    def test_preview_cannot_spend_coins_and_settings_freeze_during_run(self):
        self.app.rounds.set('5')
        self.app.dry_run.set(True)
        self.app.preview_changed()
        self.assertEqual(self.app.options().mode, 'current')
        self.assertEqual(str(self.app.mode_box['state']), 'disabled')
        self.app.set_busy(True)
        self.assertEqual(str(self.app.start_button['state']), 'disabled')
        self.assertEqual(str(self.app.stop_button['state']), 'normal')
        self.assertEqual(str(self.app.round_spin['state']), 'disabled')
        self.app.set_busy(False)
        self.app.dry_run.set(False)
        self.app.preview_changed()
        self.assertEqual(self.app.options().mode, 'current')
        self.app.mode.set('自动循环')
        self.assertEqual(self.app.options().rounds, 5)
        self.assertIn('3,000', self.app.cost.get())

    def test_editor_saves_types_and_required_flags_then_reloads(self):
        saved = []
        editor = RuleEditor(self.root, None, saved.append)
        editor.withdraw()
        editor.name.set('双暴组合')
        editor.minimum.set('2')
        editor.rows['暴击率'].set('必备')
        editor.rows['暴击伤害'].set('计入条数')
        editor.save()
        expected = KeepRule('双暴组合', (RetainCondition('暴击率', required=True), RetainCondition('暴击伤害')), 2)
        self.assertEqual(saved, [expected])
        self.app.rules = saved
        self.app.save_settings()
        data = json.loads((Path(self.folder.name) / 'settings.json').read_text(encoding='utf-8'))
        self.assertNotIn('minimum_value', json.dumps(data))
        self.assertEqual(Options.from_dict(data).rules, (expected,))
        self.app.rules = []
        self.app.load_settings()
        self.assertEqual(self.app.rules, saved)

    def test_results_explain_rule_and_round_only_completes_after_menu(self):
        self.app.target = 10
        record = dict(round=1, item=1, action='保留', matched=('暴击率', '暴击伤害'),
                      affixes=[dict(raw='暴击率提升3.00%'), dict(raw='暴击伤害提升8.00%')],
                      reason='满足双暴规则', rule_name='双暴保留', dry_run=False)
        self.app.emit('item', record)
        self.app.poll()
        self.assertEqual(self.app.kept, 1)
        self.assertEqual(self.app.completed_rounds, 0)
        self.app.show_record()
        self.assertIn('满足双暴规则', self.app.detail.get())
        self.assertIn('双暴保留', self.app.table.item(self.app.table.get_children()[0])['values'])
        self.app.emit('round_complete', dict(round=1, rounds=1))
        self.app.poll()
        self.assertEqual(self.app.completed_rounds, 1)
        self.assertIn('已返回投币页 1 轮', self.app.summary.get())
