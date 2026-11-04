from dataclasses import dataclass
from enum import Enum
import sys
import time

import cv2
import numpy as np
from rapidocr import ModelType, OCRVersion, RapidOCR
from rapidocr.ch_ppocr_rec import TextRecInput

from .rules import Affix, parse_affix
from .paths import application_directory

ROOT = application_directory()


class RecognitionError(RuntimeError):
    pass


class Scene(Enum):
    MENU = '投币页'
    ANIMATION = '动画快进页'
    RESULT = '十连结果页'
    UNKNOWN = '过渡画面或未知页面'


@dataclass(frozen=True)
class ScreenState:
    scene: Scene
    point: tuple[int, int] | None = None


def find_fast_forward(image):
    template = fast_forward_template()
    height, width = image.shape[:2]
    x0 = round(width * .90)
    region = cv2.cvtColor(image[:round(height*.13), x0:], cv2.COLOR_BGR2GRAY)
    best = None
    for factor in (.85, 1., 1.15):
        scale = width / 996 * factor
        candidate = cv2.resize(template, None, fx=scale, fy=scale)
        gray = candidate
        if gray.shape[0] > region.shape[0] or gray.shape[1] > region.shape[1]:
            continue
        scores = cv2.matchTemplate(region, gray, cv2.TM_CCOEFF_NORMED)
        _, score, _, point = cv2.minMaxLoc(scores)
        if score >= .87 and (best is None or score > best[0]):
            best = (score, (x0 + point[0] + gray.shape[1] // 2,
                            point[1] + gray.shape[0] // 2))
    return best[1] if best else None


def fast_forward_template():
    """用通用的圆形、三角形和竖线构造模板，不分发游戏截图。"""
    template = np.full((31, 31), 20, dtype=np.uint8)
    cv2.circle(template, (15, 15), 14, 40, -1, cv2.LINE_AA)
    cv2.fillPoly(template, [np.array(((9, 10), (9, 20), (17, 15)))], 225, cv2.LINE_AA)
    cv2.rectangle(template, (17, 10), (20, 20), 225, -1)
    return template


@dataclass(frozen=True)
class Text:
    text: str
    score: float
    x: float
    y: float


@dataclass(frozen=True)
class Panel:
    x: int
    y: int
    width: int

    def point(self, x: float, y: float) -> tuple[int, int]:
        return round(self.x + self.width * x), round(self.y + self.width * y)

    def crop(self, image, left, top, right, bottom):
        x1, y1 = self.point(left, top)
        x2, y2 = self.point(right, bottom)
        return image[y1:y2, x1:x2]

    @property
    def lock_point(self):
        return self.point(.90, .077)

    @property
    def discard_point(self):
        return self.point(.77, .077)

    def item_point(self, index: int):
        row, column = divmod(index, 5)
        return self.point(-2.14 + .435 * column, .47 + .50 * row)


def find_panel(image: np.ndarray) -> Panel | None:
    """从右侧橙色详情标题栏定位，随游戏窗口缩放和移动。"""
    height, width = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array((8, 160, 140)), np.array((32, 255, 255)))
    mask[:, :int(width * .55)] = 0
    mask[:int(height * .12)] = 0
    mask[int(height * .52):] = 0
    kernel = np.ones((max(3, round(width / 200)),) * 2, np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if .12 * width < w < .28 * width and 2.2 < w / h < 4.5:
            candidates.append((cv2.contourArea(contour), Panel(x, y, w)))
    return max(candidates, key=lambda p: p[0])[1] if candidates else None


def marker_active(image: np.ndarray, panel: Panel, keep: bool) -> bool:
    """已打标图标为亮色；只使用带有明确色彩/亮度的激活状态。"""
    cx, cy = panel.lock_point if keep else panel.discard_point
    radius = max(3, round(panel.width * .033))
    icon = image[cy-radius:cy+radius+1, cx-radius:cx+radius+1]
    hsv = cv2.cvtColor(icon, cv2.COLOR_BGR2HSV)
    vivid = (hsv[:, :, 1] > 100) & (hsv[:, :, 2] > 150)
    bright = (hsv[:, :, 2] > 160) & (hsv[:, :, 1] < 90)
    return float((vivid | bright).mean()) > .18


def selected_item(image: np.ndarray, panel: Panel) -> int | None:
    selected = []
    for index in range(10):
        x, y = panel.item_point(index)
        radius = round(panel.width * .215)
        if x - radius < 0 or y - radius < 0:
            return None
        tile = image[y-radius:y+radius, x-radius:x+radius]
        hsv = cv2.cvtColor(tile, cv2.COLOR_BGR2HSV)
        pink = cv2.inRange(hsv, np.array((145, 150, 150)), np.array((179, 255, 255)))
        if float((pink > 0).mean()) > .045:
            selected.append(index)
    return selected[0] if len(selected) == 1 else None


class Reader:
    def __init__(self):
        started = time.perf_counter()
        params = {
            'Det.ocr_version': OCRVersion.PPOCRV6,
            'Rec.ocr_version': OCRVersion.PPOCRV6,
            'Det.model_type': ModelType.TINY,
            'Rec.model_type': ModelType.TINY,
            'Global.use_cls': False,
            'Global.model_root_dir': str(ROOT / 'models'),
            'Global.text_score': .5,
            'Global.log_level': 'warning',
            'EngineConfig.onnxruntime.intra_op_num_threads': 2,
            'EngineConfig.onnxruntime.inter_op_num_threads': 1,
        }
        if getattr(sys, 'frozen', False):
            # 便携包自带这两个模型，缺失时明确报错，不触发额外下载。
            for task, name in [('Det', 'PP-OCRv6_det_tiny.onnx'), ('Rec', 'PP-OCRv6_rec_tiny.onnx')]:
                model = ROOT / 'models' / name
                if not model.is_file():
                    raise RecognitionError(f'便携版模型缺失：models/{name}，请完整解压下载包')
                params[f'{task}.model_path'] = str(model)
        self.engine = RapidOCR(params=params)
        # RapidOCR 延迟加载模型；用真实文字同时预热检测和识别，完成后才报告就绪。
        sample = np.full((96, 480, 3), 255, dtype=np.uint8)
        cv2.putText(sample, 'OCR123', (20, 65), cv2.FONT_HERSHEY_SIMPLEX, 1.8, (0, 0, 0), 3)
        if not any(text.text.replace(' ', '') == 'OCR123' for text in self.texts(sample)):
            raise RecognitionError('OCR 模型预热未通过，未进入游戏操作')
        self.load_seconds = time.perf_counter() - started

    def texts(self, image: np.ndarray) -> list[Text]:
        result = self.engine(image)
        if result.txts is None:
            return []
        return [Text(text, float(score), float(box[:, 0].mean()), float(box[:, 1].mean()))
                for text, score, box in zip(result.txts, result.scores, result.boxes)]

    def affixes(self, image: np.ndarray, panel: Panel) -> list[Affix]:
        # 结果面板的四行位置固定：一次批量识别四行，不再重复跑文字检测。
        rows = [panel.crop(image, .12, center-.052, .75, center+.052)
                for center in (.92, 1.045, 1.17, 1.295)]
        if any(row.size == 0 for row in rows):
            raise RecognitionError('详情面板超出画面')
        result = self.engine.text_rec(TextRecInput(img=rows))
        affixes = []
        for text, score in zip(result.txts, result.scores):
            affix = parse_affix(text)
            if affix is None or score < .88:
                raise RecognitionError(f'副属性未可靠识别：{text}（{score:.2f}）')
            affixes.append(affix)
        if len(affixes) != 4:
            raise RecognitionError(f'只识别到 {len(affixes)} 条完整副属性，需要 4 条')
        if len({affix.name for affix in affixes}) != 4:
            raise RecognitionError('识别到重复副属性，请人工核对画面')
        return affixes

    def is_result(self, image: np.ndarray) -> bool:
        height, width = image.shape[:2]
        crop = image[int(height*.23):int(height*.33), int(width*.17):int(width*.62)]
        return any('倒带获得' in t.text.replace(' ', '') for t in self.texts(crop))

    def coin_button(self, image: np.ndarray):
        height, width = image.shape[:2]
        left, top = int(width * .55), int(height * .72)
        crop = image[top:int(height*.88), left:int(width*.85)]
        crop = cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        for text in self.texts(crop):
            cleaned = text.text.replace(' ', '')
            if '投币10次' in cleaned and text.score >= .88:
                return round(left + text.x / 2), round(top + text.y / 2)
        return None

    def scene(self, image: np.ndarray) -> ScreenState:
        # 结果面板出现时优先确认，避免转场中的快进图标残影覆盖结果页状态。
        if find_panel(image) is not None and self.is_result(image):
            return ScreenState(Scene.RESULT)
        point = find_fast_forward(image)
        if point is not None:
            return ScreenState(Scene.ANIMATION, point)
        point = self.coin_button(image)
        if point is not None:
            return ScreenState(Scene.MENU, point)
        return ScreenState(Scene.UNKNOWN)
