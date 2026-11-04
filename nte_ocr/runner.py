from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
import threading
import time

import cv2

from .rules import DEFAULT_RETAIN_STATS, KeepRule, RetainCondition, default_rules, decide
from .paths import application_directory
from .vision import Reader, RecognitionError, Scene, find_panel, marker_active, selected_item
from .windows import GameWindow, WindowError

ROOT = application_directory()


class Stopped(RuntimeError):
    pass


@dataclass(frozen=True)
class Options:
    mode: str = 'loop'
    rounds: int = 1
    dry_run: bool = False
    rules: tuple[KeepRule, ...] = field(default_factory=default_rules)

    def validate(self):
        if self.mode not in ('current', 'loop'):
            raise ValueError('运行模式无效')
        if type(self.dry_run) is not bool:
            raise ValueError('预览状态须为是或否')
        if self.dry_run and self.mode == 'loop':
            raise ValueError('预览只处理当前结果页；循环投币前请关闭“仅预览”')
        if type(self.rounds) is not int or not 1 <= self.rounds <= 999:
            raise ValueError('轮数须在 1～999 之间')
        if not any(rule.enabled for rule in self.rules):
            raise ValueError('请至少启用一条保留规则')
        for rule in self.rules:
            rule.validate()

    @classmethod
    def from_dict(cls, data):
        data = dict(data)
        data.pop('click_delay', None)
        if 'rules' in data:
            data['rules'] = tuple(KeepRule.from_dict(rule) for rule in data['rules'])
        else:
            stats = data.pop('good_stats', DEFAULT_RETAIN_STATS)
            minimum = data.pop('minimum', 3)
            double_crit = data.pop('keep_double_crit', True)
            rules = []
            if double_crit and {'暴击率', '暴击伤害'}.issubset(stats):
                rules.append(default_rules()[0])
            if stats:
                name = '四项中至少三项' if tuple(stats) == DEFAULT_RETAIN_STATS and minimum == 3 else f'保留词条至少 {minimum} 条'
                rules.append(KeepRule(name, tuple(RetainCondition(s) for s in stats), minimum))
            data['rules'] = tuple(rules)
        options = cls(**data)
        options.validate()
        return options


class Runner:
    def __init__(self, window: GameWindow, reader: Reader, options: Options,
                 stop: threading.Event, emit):
        options.validate()
        self.window, self.reader, self.options = window, reader, options
        self.stop, self.emit = stop, emit
        folder = ROOT / 'logs'
        folder.mkdir(exist_ok=True)
        self.log_path = folder / f'{datetime.now():%Y%m%d-%H%M%S-%f}.jsonl'
        self.trace_path = self.log_path.with_suffix('.trace.jsonl')

    def trace(self, event, **details):
        record = dict(time=datetime.now().isoformat(timespec='milliseconds'), event=event, **details)
        with self.trace_path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + '\n')

    def fail(self, message, image):
        path = self.log_path.with_suffix('.failure.png')
        encoded, data = cv2.imencode('.png', image)
        if encoded:
            path.write_bytes(data.tobytes())
        self.trace('error', message=message, screenshot=str(path))
        raise RecognitionError(f'{message}。现场截图：{path.name}')

    def frame(self):
        if self.stop.is_set():
            raise Stopped('已停止')
        return self.window.capture()

    def click(self, point, rect, *, aligned=False):
        if self.stop.is_set():
            raise Stopped('已停止')
        started = time.perf_counter()
        if aligned:
            self.window.click_aligned(point, rect)
        else:
            self.window.click(point, rect)
        self.trace('click', client_point=point, method='窗口移位模拟' if aligned else '后台消息',
                   input_ms=round((time.perf_counter()-started)*1000, 1))

    def result_frame(self):
        image, rect = self.frame()
        panel = find_panel(image)
        if panel is None or not self.reader.is_result(image):
            raise RecognitionError('未确认十连结果页，未发送打标；自动模式可从投币页、动画页和结果页接续')
        return image, rect, panel

    def reach_result(self):
        deadline = time.monotonic() + 45
        pending, action_time, previous = None, 0., None
        while True:
            image, rect = self.frame()
            state = self.reader.scene(image)
            now = time.monotonic()
            if state.scene != previous:
                self.trace('scene', scene=state.scene.value)
                self.emit('status', f'当前识别：{state.scene.value}')
                previous = state.scene
            if state.scene == Scene.RESULT:
                return
            if now >= deadline:
                self.fail(f'接续超时，最后识别为“{state.scene.value}”', image)
            if state.scene == Scene.MENU:
                if pending == Scene.MENU:
                    if now-action_time > 4:
                        self.fail('投币器点击后页面未变化，游戏未响应后台投币；未重复投币', image)
                elif pending == Scene.ANIMATION:
                    self.fail('快进后返回投币页，但未捕获到结果页，已停止核对', image)
                else:
                    self.emit('status', '窗口移位模拟投币，鼠标保持原位…')
                    self.click(state.point, rect, aligned=True)
                    pending, action_time = Scene.MENU, time.monotonic()
            elif state.scene == Scene.ANIMATION:
                if pending == Scene.ANIMATION:
                    if now-action_time > 5:
                        self.fail('快进点击后画面未变化，游戏未响应后台快进', image)
                else:
                    self.emit('status', '识别到动画，点击快进…')
                    pending, action_time = Scene.ANIMATION, time.monotonic()
                    # 每段动画只发一次。截图可能滞后一帧，重复点击会关闭刚出现的结果页。
                    self.click(state.point, rect, aligned=True)

    def close_result(self):
        image, rect, _ = self.result_frame()
        height, width = image.shape[:2]
        self.click((round(width * .5), round(height * .89)), rect, aligned=True)
        deadline = time.monotonic() + 8
        while True:
            image, _ = self.frame()
            if self.reader.scene(image).scene == Scene.MENU:
                return
            if time.monotonic() >= deadline:
                self.fail('关闭结果页后未回到投币页，已停止，避免重复处理同一批', image)

    def wait_selected(self, rect, panel, index):
        deadline, previous = time.monotonic()+3, None
        while True:
            image, current_rect = self.frame()
            if current_rect != rect:
                raise WindowError('处理过程中窗口布局发生变化，已停止')
            if find_panel(image) == panel and selected_item(image, panel) == index:
                current = panel.crop(image, .10, .84, .79, 1.365)
                # 连续两帧副属性相同即可读取，不使用固定秒数等待。
                if previous is not None and cv2.norm(previous, current, cv2.NORM_L1) == 0:
                    return image
                previous = current.copy()
            else:
                previous = None
            if time.monotonic() >= deadline:
                self.fail(f'第 {index+1} 件选中或词条画面未就绪，未发送打标', image)

    def wait_marker(self, rect, panel, index, keep):
        deadline = time.monotonic()+3
        while True:
            image, current_rect = self.frame()
            if current_rect != rect or find_panel(image) != panel or selected_item(image, panel) != index:
                raise RecognitionError('打标确认时布局或选中项发生变化，已停止')
            if marker_active(image, panel, keep):
                return
            if time.monotonic() >= deadline:
                self.fail(f'第 {index+1} 件未确认打标完成，已停止', image)

    def process_result(self, round_number):
        image, rect, panel = self.result_frame()
        for index in range(10):
            started = time.perf_counter()
            self.click(panel.item_point(index), rect)
            image = self.wait_selected(rect, panel, index)
            ocr_started = time.perf_counter()
            affixes = self.reader.affixes(image, panel)
            ocr_ms = round((time.perf_counter()-ocr_started)*1000, 1)
            decision = decide(affixes, self.options.rules)
            keep = decision.keep
            active = marker_active(image, panel, keep)
            opposite = marker_active(image, panel, not keep)
            action = '保留' if keep else '丢弃'
            if not self.options.dry_run:
                if opposite:
                    raise RecognitionError(f'第 {index+1} 件已有相反标记，已停止供人工核对')
                if not active:
                    point = panel.lock_point if keep else panel.discard_point
                    self.click(point, rect)
                    self.wait_marker(rect, panel, index, keep)
            record = dict(time=datetime.now().isoformat(timespec='seconds'), round=round_number,
                          item=index+1, action=action, dry_run=self.options.dry_run,
                          affixes=[asdict(a) for a in affixes], matched=decision.matched,
                          reason=decision.reason, rule_name=decision.rule_name, ocr_ms=ocr_ms,
                          item_ms=round((time.perf_counter()-started)*1000, 1))
            with self.log_path.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + '\n')
            self.emit('item', record)

    def run(self):
        rounds = 1 if self.options.mode == 'current' else self.options.rounds
        for number in range(1, rounds + 1):
            if self.options.mode == 'loop':
                self.emit('status', f'第 {number}/{rounds} 轮：识别当前循环界面并接续')
                self.reach_result()
            self.emit('status', f'第 {number}/{rounds} 轮：逐个读取并判定')
            self.process_result(number)
            self.emit('status', f'第 {number}/{rounds} 轮：打标结束，返回投币页…')
            self.close_result()
            self.emit('round_complete', dict(round=number, rounds=rounds))
        self.emit('status', f'完成，共 {rounds} 轮。记录：{self.log_path.name}')
