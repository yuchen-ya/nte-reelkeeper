from pathlib import Path
import os

from PyInstaller.utils.hooks import collect_data_files

project = Path(SPECPATH).parent
baseline = os.environ.get('REELKEEPER_BUILD_BASELINE') == '1'

analysis = Analysis(
    [str(project / 'main.py')],
    pathex=[str(project)],
    datas=collect_data_files('rapidocr'),
    hiddenimports=['rapidocr.main', 'onnxruntime'],
    excludes=[
        'rapidocr.inference_engine.pytorch', 'rapidocr.inference_engine.paddle',
        'rapidocr.inference_engine.openvino', 'rapidocr.inference_engine.tensorrt',
        'rapidocr.inference_engine.mnn',
    ] + ([] if baseline else [
        # 截图试算仅支持 PNG / JPEG / BMP，不分发额外的 AVIF / WebP 编解码器。
        'PIL.AvifImagePlugin', 'PIL._avif', 'PIL.WebPImagePlugin', 'PIL._webp',
    ]),
    # 自身模块独立为字节码文件，日后更新不必重下整个 Python 依赖归档。
    noarchive=not baseline,
)
if not baseline:
    analysis.datas = [item for item in analysis.datas
                      if not (item[0].replace('\\', '/').startswith('rapidocr/models/')
                              and item[0].endswith('.onnx'))]
    analysis.binaries = [item for item in analysis.binaries
                         if not Path(item[0]).name.lower().startswith('opencv_videoio_ffmpeg')]

pyz = PYZ(analysis.pure)
exe = EXE(
    pyz, analysis.scripts, [],
    exclude_binaries=True, name='ReelKeeper', debug=False, strip=False,
    upx=False, console=False,
)
collection = COLLECT(
    exe, analysis.binaries, analysis.datas,
    strip=False, upx=False, name='ReelKeeper',
)
