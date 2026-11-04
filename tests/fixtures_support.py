import os
from pathlib import Path
import unittest


def screenshot_fixtures():
    configured = os.environ.get('REELKEEPER_TEST_FIXTURES')
    folder = Path(configured) if configured else Path(__file__).parent / 'fixtures'
    if not configured and not folder.exists():
        raise unittest.SkipTest('私有截图未提供；参见 docs/testing.md')
    names = ('menu', 'menu_live', 'animation', 'result_a', 'result_b', 'detail_a', 'detail_b', 'detail_tilt')
    missing = [name + '.png' for name in names if not (folder / (name + '.png')).is_file()]
    if missing:
        raise FileNotFoundError('截图样本不完整：' + '、'.join(missing))
    return folder
