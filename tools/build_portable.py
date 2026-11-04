"""从隔离构建环境生成便携目录及可独立下载的组件，不复制本机运行数据。"""
import argparse
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from nte_ocr import __version__


def copy_licenses(destination):
    for distribution in metadata.distributions():
        name = distribution.metadata['Name']
        for relative in distribution.files or []:
            if not any(word in relative.name.lower() for word in ('license', 'licence', 'copying', 'notice')):
                continue
            source = Path(distribution.locate_file(relative))
            if source.is_file() and source.suffix.lower() not in ('.py', '.pyc', '.pyd', '.dll'):
                target = destination / name / str(relative).replace('..', '_parent_')
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
    base = Path(sys.base_prefix)
    for source in [base / 'LICENSE.txt', *base.glob('tcl/**/license.terms')]:
        target = destination / 'Python-Tcl-Tk' / source.relative_to(base)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def make_zip(path, folder, files):
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for source in sorted(files):
            info = zipfile.ZipInfo((Path('ReelKeeper') / source.relative_to(folder)).as_posix())
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, source.read_bytes(), compresslevel=9)
    return path.stat().st_size


def main():
    if sys.platform != 'win32' or sys.version_info[:2] != (3, 12):
        raise RuntimeError('请使用标准 Windows CPython 3.12 x64 构建已验证的便携版')
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', action='store_true', help='保留闲置模型及视频 DLL，仅用于体积比较')
    parser.add_argument('--seven-zip', type=Path, help='可选 7z / 7zr 可执行文件，额外生成更小的 7z 全量包')
    parser.add_argument('--output-root', type=Path, default=ROOT / 'dist', help='构建输出目录')
    args = parser.parse_args()
    mode = 'baseline' if args.baseline else 'portable'
    output = args.output_root.resolve() / mode
    environment = dict(os.environ, REELKEEPER_BUILD_BASELINE='1' if args.baseline else '0')
    subprocess.run([
        sys.executable, '-m', 'PyInstaller', '--noconfirm',
        '--distpath', str(output), '--workpath', str(ROOT / 'build' / mode),
        str(ROOT / 'packaging' / 'ReelKeeper.spec'),
    ], cwd=ROOT, env=environment, check=True)
    folder = output / 'ReelKeeper'
    model_directory = folder / 'models'
    model_directory.mkdir(exist_ok=True)
    for name in ('PP-OCRv6_det_tiny.onnx', 'PP-OCRv6_rec_tiny.onnx'):
        shutil.copy2(ROOT / 'models' / name, model_directory / name)
    copy_licenses(folder / '_internal' / 'licenses')
    model_licenses = model_directory / 'licenses'
    model_licenses.mkdir(exist_ok=True)
    shutil.copy2(ROOT / 'packaging' / 'model-notice.md', model_licenses / 'NOTICE.md')
    shutil.copy2(ROOT / 'packaging' / 'licenses' / 'PaddleOCR-LICENSE', model_licenses / 'PaddleOCR-LICENSE')
    rapidocr_distribution = metadata.distribution('rapidocr')
    rapidocr_notice = next(file for file in rapidocr_distribution.files if file.name == 'MODEL_LICENSES.md')
    shutil.copy2(rapidocr_distribution.locate_file(rapidocr_notice), model_licenses / 'RapidOCR-MODEL_LICENSES.md')
    for name in ('LICENSE', 'THIRD_PARTY_NOTICES.md'):
        shutil.copy2(ROOT / name, folder / name)
    (folder / '使用说明.txt').write_text(
        'ReelKeeper ' + __version__ + '\n\n'
        '完整解压到可写目录，双击 ReelKeeper.exe。无需安装 Python，模型已包含，可离线识别。\n'
        '请保留 _internal 和 models 文件夹，其中包含运行库与许可证。F8 开始，F9 停止。\n'
        '自动循环会消耗游戏金币；丢弃只打标，不分解。\n'
        '个人设置和日志保存在 EXE 旁的 settings.json、logs/，更新时保留。\n'
        '组件包必须来自同一次构建，解压到同一个目录；没有自动更新器。\n'
        '安装自检：ReelKeeper.exe --check-installation 检查报告.json，不操作游戏。\n', encoding='utf-8-sig')
    files = [p for p in folder.rglob('*') if p.is_file()]
    full_name = f'ReelKeeper-{__version__}-windows-x64' + ('-baseline' if args.baseline else '')
    metrics = dict(version=__version__, baseline=args.baseline, directory_bytes=sum(p.stat().st_size for p in files))
    metrics['full_zip_bytes'] = make_zip(output / (full_name + '.zip'), folder, files)
    if not args.baseline:
        def app_file(path):
            parts = path.relative_to(folder).parts
            return parts[0] not in ('_internal', 'models') or parts[:2] == ('_internal', 'nte_ocr')

        groups = {
            'engine': [p for p in files if p.relative_to(folder).parts[0] == '_internal' and not app_file(p)],
            'models': [p for p in files if p.relative_to(folder).parts[0] == 'models'],
            'app': [p for p in files if app_file(p)],
        }
        metrics['components'] = {}
        for name, members in groups.items():
            filename = full_name + '-' + name + '.zip'
            component = output / filename
            metrics['components'][name] = dict(file=filename, bytes=make_zip(component, folder, members),
                                              sha256=hashlib.sha256(component.read_bytes()).hexdigest())
        (output / 'components.json').write_text(json.dumps(dict(version=__version__, components=metrics['components']),
                                                           ensure_ascii=False, indent=2), encoding='utf-8')
    if args.seven_zip:
        seven_zip = args.seven_zip.resolve(strict=True)
        compressed = output / (full_name + '.7z')
        if compressed.exists():
            raise FileExistsError(f'请使用新的输出目录或手动移走已有归档：{compressed}')
        subprocess.run([str(seven_zip), 'a', '-t7z', '-mx=9', '-md=64m', '-mmt=2',
                        str(compressed), 'ReelKeeper'], cwd=output, check=True)
        metrics['full_7z_bytes'] = compressed.stat().st_size
    (output / 'sizes.json').write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
