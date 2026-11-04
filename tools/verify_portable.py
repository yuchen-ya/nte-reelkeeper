"""从三个组件重建便携版，检查中文路径、配置持久化、离线识别及缺失模型错误。"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import zipfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('package_directory', type=Path)
    parser.add_argument('--work-directory', type=Path, required=True, help='必须是尚不存在的验证目录')
    parser.add_argument('--fixtures', type=Path, help='可选私有截图目录，不会打入分发包')
    args = parser.parse_args()
    package_directory = args.package_directory.resolve()
    work = args.work_directory.resolve()
    work.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((package_directory / 'components.json').read_text(encoding='utf-8'))
    if set(manifest['components']) != {'engine', 'models', 'app'}:
        raise ValueError('组件清单不完整')
    members = set()
    for component in manifest['components'].values():
        archive_path = (package_directory / component['file']).resolve()
        if archive_path.parent != package_directory:
            raise ValueError('组件文件必须位于分发目录中')
        data = archive_path.read_bytes()
        if len(data) != component['bytes'] or hashlib.sha256(data).hexdigest() != component['sha256']:
            raise ValueError(f'组件大小或校验不一致：{archive_path.name}')
        with zipfile.ZipFile(archive_path) as archive:
            for name in archive.namelist():
                path = PurePosixPath(name)
                if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] != 'ReelKeeper':
                    raise ValueError('组件包含无效路径')
                if name in members:
                    raise ValueError(f'组件文件重复：{name}')
                members.add(name)
            archive.extractall(work)
    folder = work / 'ReelKeeper'
    executable = folder / 'ReelKeeper.exe'
    models = list(folder.rglob('*.onnx'))
    if len(models) != 2 or any('small' in p.name or 'cls' in p.name for p in models):
        raise ValueError('便携包应只包含两个 Tiny 模型')
    if list(folder.rglob('*ffmpeg*.dll')):
        raise ValueError('视频库未排除')
    settings = dict(mode='current', rounds=7, dry_run=True)
    (folder / 'settings.json').write_text(json.dumps(settings), encoding='utf-8')

    def check(name, extra=(), expected_status=0):
        report = work / (name + '.json')
        result = subprocess.run([str(executable), '--check-installation', str(report), *extra], cwd=work, timeout=60)
        if result.returncode != expected_status:
            details = report.read_text(encoding='utf-8') if report.exists() else '没有生成报告'
            raise RuntimeError(details)
        return json.loads(report.read_text(encoding='utf-8'))

    extra = []
    if args.fixtures:
        for name in ('menu', 'animation', 'result_a', 'result_b', 'detail_a', 'detail_b', 'detail_tilt'):
            extra += ['--check-image', str((args.fixtures / (name + '.png')).resolve(strict=True))]
    first = check('first-start', extra)
    if not first['ok'] or Path(first['application_directory']).resolve() != folder:
        raise RuntimeError('便携版根目录或运行依赖检查未通过')
    if first['settings'] != settings:
        raise RuntimeError('没有读取 EXE 旁的个人配置')
    if args.fixtures:
        images = {item['file']: item for item in first['images']}
        for name, scene in [('menu.png', '投币页'), ('animation.png', '动画快进页'),
                            ('result_a.png', '十连结果页'), ('result_b.png', '十连结果页')]:
            if images[name]['scene'] != scene:
                raise RuntimeError(f'页面识别错误：{name}')
        for name, keep in [('detail_a.png', True), ('detail_b.png', False), ('detail_tilt.png', False),
                           ('result_a.png', False), ('result_b.png', False)]:
            if images[name]['keep'] != keep or len(images[name]['affixes']) != 4:
                raise RuntimeError(f'副属性或默认规则不一致：{name}')
        if images['result_a.png']['selected_item'] != 0 or images['result_b.png']['selected_item'] != 5:
            raise RuntimeError('选中物品识别不一致')
    second = check('second-start')
    if second['settings'] != settings:
        raise RuntimeError('再次启动时配置未保留')
    missing = folder / 'models' / 'PP-OCRv6_rec_tiny.onnx'
    disabled = missing.with_suffix('.disabled')
    missing.rename(disabled)
    try:
        failed = check('missing-model', expected_status=1)
        if failed['ok'] or 'PP-OCRv6_rec_tiny.onnx' not in failed['error']:
            raise RuntimeError('缺失模型时未明确报错')
    finally:
        disabled.rename(missing)
    print(json.dumps(dict(ok=True, component_reassembly=True, chinese_path=str(work),
                          images=len(first['images']), persistent_settings=True, missing_model_rejected=True),
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
