from dataclasses import dataclass
import re
import unicodedata


DEFAULT_RETAIN_STATS = ('暴击率', '暴击伤害', '伤害增加', '攻击力百分比')
STAT_LABELS = {
    '暴击率': '暴击率（%）', '暴击伤害': '暴击伤害（%）', '伤害增加': '伤害增加（%）',
    '攻击力百分比': '攻击力（%）', '生命值百分比': '生命值（%）', '防御力百分比': '防御力（%）',
    '攻击力固定值': '攻击力（固定值）', '生命值固定值': '生命值（固定值）',
    '防御力固定值': '防御力（固定值）', '环合强度': '环合强度', '倾陷强度': '倾陷强度',
}


@dataclass(frozen=True)
class RetainCondition:
    stat: str
    required: bool = False


@dataclass(frozen=True)
class KeepRule:
    name: str
    conditions: tuple[RetainCondition, ...]
    minimum_matches: int = 1
    enabled: bool = True

    def validate(self):
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError('请填写规则名称')
        if type(self.enabled) is not bool:
            raise ValueError('规则的启用状态必须为是或否')
        if type(self.minimum_matches) is not int or not 1 <= self.minimum_matches <= 4:
            raise ValueError('命中数量须为 1～4 条')
        if len(self.conditions) < self.minimum_matches:
            raise ValueError('选择的保留词条数量少于要求的命中数量')
        if len({c.stat for c in self.conditions}) != len(self.conditions):
            raise ValueError('同一条规则不能重复选择相同词条')
        for condition in self.conditions:
            if condition.stat not in STAT_LABELS:
                raise ValueError(f'不支持的保留词条：{condition.stat}')
            if type(condition.required) is not bool:
                raise ValueError('必备词条状态必须为是或否')
        if sum(c.required for c in self.conditions) > 4:
            raise ValueError('驱动块只有四条副属性，不能要求超过四条必备词条')

    @classmethod
    def from_dict(cls, data):
        conditions = []
        for item in data['conditions']:
            condition = dict(item)
            # 兼容已保存的旧配置：移除数值条件，保留词条类型与必备状态。
            condition.pop('minimum_value', None)
            conditions.append(RetainCondition(**condition))
        rule = cls(name=data['name'], conditions=tuple(conditions),
                   minimum_matches=data['minimum_matches'], enabled=data['enabled'])
        rule.validate()
        return rule


def default_rules():
    return (
        KeepRule('双暴保留', tuple(RetainCondition(s, required=True) for s in ('暴击率', '暴击伤害')), 2),
        KeepRule('四项中至少三项', tuple(RetainCondition(s) for s in DEFAULT_RETAIN_STATS), 3),
    )


def describe_rule(rule: KeepRule) -> str:
    parts = []
    for condition in rule.conditions:
        label = STAT_LABELS[condition.stat]
        if condition.required:
            label += '【必备】'
        parts.append(label)
    return f'以下词条至少满足 {rule.minimum_matches} 条，必备项必须全部满足：\n' + '、'.join(parts)


@dataclass(frozen=True)
class Affix:
    name: str
    value: float
    percent: bool
    raw: str


@dataclass(frozen=True)
class Decision:
    keep: bool
    matched: tuple[str, ...]
    reason: str
    rule_name: str = ''


def parse_affix(text: str) -> Affix | None:
    """仅接受完整可识别的词条；固定攻击和百分比攻击分别处理。"""
    cleaned = re.sub(r'\s+', '', unicodedata.normalize('NFKC', text))
    match = re.fullmatch(
        r'(暴击伤害|暴击率|伤害|攻击力|生命值|防御力|环合强度|倾陷强度)(提升|增加)(\d+(?:\.\d+)?)(%)?',
        cleaned,
    )
    if not match:
        return None
    stat, verb, number, percent_sign = match.groups()
    percent = bool(percent_sign)
    value = float(number)
    if value <= 0 or (not percent and not value.is_integer()):
        return None
    if stat in ('暴击率', '暴击伤害', '伤害') and not percent:
        return None
    if verb == '提升' and not percent:
        return None
    name = {'伤害': '伤害增加'}.get(stat, stat)
    if stat in ('攻击力', '生命值', '防御力'):
        name = stat + ('百分比' if percent else '固定值')
    return Affix(name, value, percent, text)


def decide(affixes: list[Affix], rules=None) -> Decision:
    if len(affixes) != 4:
        raise ValueError('必须完整识别四条副属性后才能判定')
    rules = default_rules() if rules is None else rules
    names = {a.name for a in affixes}
    all_matched, misses = set(), []
    for rule in rules:
        if not rule.enabled:
            continue
        matched = tuple(c.stat for c in rule.conditions if c.stat in names)
        missing = [STAT_LABELS[c.stat] for c in rule.conditions if c.required and c.stat not in matched]
        all_matched.update(matched)
        if not missing and len(matched) >= rule.minimum_matches:
            return Decision(True, matched, f'满足“{rule.name}”：命中 {len(matched)} 种保留词条，必备项全部满足', rule.name)
        reason = f'“{rule.name}”命中 {len(matched)}/{rule.minimum_matches} 条'
        if missing:
            reason += '，未满足必备：' + '、'.join(missing)
        misses.append(reason)
    return Decision(False, tuple(sorted(all_matched)), '未满足保留规则：' + '；'.join(misses))
