from dataclasses import asdict, replace
import itertools
import json
import unittest

from nte_ocr.rules import Affix, DEFAULT_RETAIN_STATS, KeepRule, RetainCondition, default_rules, decide, parse_affix
from nte_ocr.runner import Options


class RuleTests(unittest.TestCase):
    def test_every_default_retain_combination(self):
        for count in range(5):
            for combination in itertools.combinations(DEFAULT_RETAIN_STATS, count):
                with self.subTest(combination=combination):
                    affixes = [Affix(name, 4, True, name) for name in combination]
                    affixes += [Affix(f'普通词条{i}', 24, False, '') for i in range(4-count)]
                    expected = count >= 3 or {'暴击率', '暴击伤害'}.issubset(combination)
                    self.assertEqual(decide(affixes).keep, expected)

    def test_percentage_attack_is_distinct_from_flat_attack(self):
        self.assertEqual(parse_affix('攻击力提升3.75%').name, '攻击力百分比')
        self.assertEqual(parse_affix('攻击力增加5.00％').name, '攻击力百分比')
        self.assertEqual(parse_affix('攻击力增加32').name, '攻击力固定值')

    def test_tilt_strength_is_valid_but_not_in_default_retain_stats(self):
        affix = parse_affix('倾陷强度增加12')
        self.assertEqual(affix.name, '倾陷强度')
        self.assertEqual(affix.value, 12)
        self.assertNotIn(affix.name, DEFAULT_RETAIN_STATS)

    def test_incomplete_or_corrupted_affix_is_rejected(self):
        for text in ('攻击力提升3.75', '伤害增加4.00', '暴击率提升', '攻击力增加3.75',
                     '暴击伤害提升8.00%乱码', '防御力增加0'):
            with self.subTest(text=text):
                self.assertIsNone(parse_affix(text))
        with self.assertRaises(ValueError):
            decide([Affix('暴击率', 4, True, '')])

    def affixes(self, *texts):
        return [parse_affix(text) for text in texts]

    def test_required_stat_overrides_count(self):
        affixes = self.affixes('暴击率提升3.00%', '暴击伤害提升8.00%', '伤害增加4.00%', '攻击力增加32')
        rule = KeepRule('暴击率必备', (RetainCondition('暴击率', required=True), RetainCondition('暴击伤害'),
                                     RetainCondition('伤害增加')), 2)
        decision = decide(affixes, (rule,))
        self.assertTrue(decision.keep)
        self.assertEqual(decision.rule_name, rule.name)
        affixes[0] = parse_affix('生命值增加224')
        self.assertFalse(decide(affixes, (rule,)).keep)
        self.assertIn('未满足必备', decide(affixes, (rule,)).reason)

    def test_any_enabled_rule_can_match(self):
        affixes = self.affixes('环合强度增加24', '攻击力增加32', '伤害增加4.00%', '生命值增加224')
        custom = KeepRule('环合词条', (RetainCondition('环合强度', required=True), RetainCondition('攻击力固定值')), 2)
        self.assertFalse(decide(affixes).keep)
        self.assertTrue(decide(affixes, (*default_rules(), custom)).keep)
        self.assertFalse(decide(affixes, (*default_rules(), replace(custom, enabled=False))).keep)

    def test_flat_attack_never_counts_as_percent(self):
        affixes = self.affixes('暴击率提升3.00%', '攻击力增加32', '防御力增加16', '生命值增加224')
        rule = KeepRule('百分比攻击', (RetainCondition('暴击率'), RetainCondition('攻击力百分比')), 2)
        self.assertFalse(decide(affixes, (rule,)).keep)

    def test_same_types_have_same_decision_across_block_values(self):
        examples = [
            (('暴击率提升2.00%', '暴击伤害提升4.00%', '防御力增加16', '生命值增加112'),
             ('暴击率提升4.00%', '暴击伤害提升8.00%', '防御力增加32', '生命值增加224'), True),
            (('暴击率提升2.00%', '伤害增加2.00%', '攻击力提升2.50%', '防御力增加16'),
             ('暴击率提升4.00%', '伤害增加4.00%', '攻击力提升5.00%', '防御力增加32'), True),
            (('暴击率提升2.00%', '攻击力增加16', '防御力提升3.50%', '生命值增加112'),
             ('暴击率提升4.00%', '攻击力增加32', '防御力提升7.00%', '生命值增加224'), False),
        ]
        for small, large, expected in examples:
            with self.subTest(small=small):
                decision = decide(self.affixes(*small))
                self.assertEqual(decision.keep, expected)
                self.assertEqual(decision, decide(self.affixes(*large)))

    def test_all_fixed_and_percent_types_are_distinct(self):
        for stat in ('攻击力', '生命值', '防御力'):
            with self.subTest(stat=stat):
                self.assertEqual(parse_affix(f'{stat}增加16').name, stat + '固定值')
                self.assertEqual(parse_affix(f'{stat}提升3.50%').name, stat + '百分比')

    def test_invalid_rule_cannot_be_saved(self):
        good = default_rules()[0]
        cases = [replace(good, name=' '), replace(good, minimum_matches=0),
                 replace(good, minimum_matches=3), replace(good, minimum_matches=True),
                 replace(good, conditions=(RetainCondition('暴击率'), RetainCondition('暴击率'))),
                 replace(good, conditions=(RetainCondition('未知'), RetainCondition('伤害增加')))]
        cases.append(replace(good, conditions=(RetainCondition('暴击率', required='是'), RetainCondition('伤害增加'))))
        for rule in cases:
            with self.subTest(rule=rule), self.assertRaises(ValueError):
                rule.validate()
        with self.assertRaises(ValueError):
            Options(rules=tuple(replace(r, enabled=False) for r in default_rules())).validate()

    def test_settings_round_trip_and_legacy_migration_preserve_behavior(self):
        legacy = dict(mode='loop', rounds=5, dry_run=False, good_stats=list(DEFAULT_RETAIN_STATS),
                      minimum=3, keep_double_crit=True, click_delay=.35)
        migrated = Options.from_dict(legacy)
        restored = Options.from_dict(json.loads(json.dumps(asdict(migrated))))
        self.assertEqual(restored, migrated)
        self.assertEqual(restored.rounds, 5)
        for count in range(5):
            for names in itertools.combinations(DEFAULT_RETAIN_STATS, count):
                affixes = [Affix(n, 4, True, n) for n in names]
                affixes += [Affix(f'其他{i}', 24, False, '') for i in range(4-count)]
                self.assertEqual(decide(affixes, restored.rules).keep, decide(affixes).keep)

    def test_custom_types_survive_settings_reload(self):
        rule = KeepRule('我的规则', (RetainCondition('暴击率', required=True), RetainCondition('生命值百分比')), 2)
        options = Options(mode='current', dry_run=True, rules=(rule,))
        self.assertEqual(Options.from_dict(json.loads(json.dumps(asdict(options)))), options)

    def test_legacy_value_limits_are_removed_on_reload(self):
        data = dict(mode='current', rules=[dict(name='双暴保留', minimum_matches=2, enabled=True, conditions=[
            dict(stat='暴击率', minimum_value=99, required=True),
            dict(stat='暴击伤害', minimum_value=99, required=True)])])
        options = Options.from_dict(data)
        affixes = self.affixes('暴击率提升2.00%', '暴击伤害提升4.00%', '防御力增加16', '生命值增加112')
        self.assertTrue(decide(affixes, options.rules).keep)
        self.assertNotIn('minimum_value', json.dumps(asdict(options)))
