from dataclasses import asdict
import json
from pathlib import Path
import traceback

from . import __version__
from .paths import application_directory


def check_installation(report_path: Path, image_paths: list[Path]):
    """只验证本地运行依赖与截图识别，不创建输入会话或发送游戏点击。"""
    report = dict(version=__version__, ok=False, images=[])
    try:
        import tkinter as tk
        from tkinter import ttk
        import cv2
        import numpy as np
        import windows_capture

        from .rules import decide, parse_affix
        from .runner import Options
        from .vision import Reader, find_panel, selected_item

        root = tk.Tk()
        root.withdraw()
        try:
            ttk.Style(root).theme_use('clam')
            report['tk_version'] = str(root.tk.call('info', 'patchlevel'))
        finally:
            root.destroy()
        report['application_directory'] = str(application_directory())
        settings = application_directory() / 'settings.json'
        if settings.is_file():
            options = Options.from_dict(json.loads(settings.read_text(encoding='utf-8')))
            report['settings'] = dict(mode=options.mode, rounds=options.rounds, dry_run=options.dry_run)
        report['capture_available'] = hasattr(windows_capture, 'WindowsCapture')
        if not report['capture_available']:
            raise RuntimeError('WindowsCapture 不可用')
        for name in ('PP-OCRv6_det_tiny.onnx', 'PP-OCRv6_rec_tiny.onnx'):
            if not (application_directory() / 'models' / name).is_file():
                raise FileNotFoundError(f'本地模型缺失：models/{name}')
        reader = Reader()
        report['ocr_load_seconds'] = round(reader.load_seconds, 3)
        for path in image_paths:
            image = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError(f'无法读取截图：{path.name}')
            record = dict(file=path.name, scene=reader.scene(image).scene.value)
            panel = find_panel(image)
            if panel is not None and reader.is_result(image):
                affixes = reader.affixes(image, panel)
                record['selected_item'] = selected_item(image, panel)
            else:
                affixes = [a for t in sorted(reader.texts(image), key=lambda t: t.y)
                           if t.score >= .88 and (a := parse_affix(t.text)) is not None]
            if affixes:
                decision = decide(affixes)
                record.update(affixes=[asdict(a) for a in affixes], keep=decision.keep)
            report['images'].append(record)
        report['ok'] = True
    except Exception:
        # 命令行诊断边界：把失败原因写入报告并返回非零状态，不隐藏或重试。
        report['error'] = traceback.format_exc()
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if report['ok'] else 1
