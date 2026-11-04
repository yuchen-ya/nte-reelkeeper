# 构建与分发

项目提供源码包、Windows x64 便携全量包，以及 app / engine / models 组件包。便携版无需另装 Python，已经包含两个 Tiny 模型。当前不含自动下载或自动更新器，也不会自动发布到 GitHub 或服务器。

## 在隔离环境构建

使用标准 Windows CPython 3.12 x64，不要复用日常运行环境安装打包工具：

```powershell
py -3.12 -m venv .venv-build
.\.venv-build\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv-build\Scripts\python.exe -c "from nte_ocr.vision import Reader; Reader()"
.\.venv-build\Scripts\python.exe tools/build_portable.py
```

最后一步输出到 `dist/portable/`。模型准备需要联网，之后构建和便携运行均使用本地文件。未改变、量化或替换模型。

可选提供本机 7-Zip / 7zr 路径，额外生成更小的 7z 全量包：

```powershell
.\.venv-build\Scripts\python.exe tools/build_portable.py --seven-zip 'C:\path\to\7z.exe' --output-root dist/release
```

7-Zip 只作为构建工具，不放入分发包。构建脚本遇到已存在的 7z 归档会停止，避免旧文件残留；重建可用新的 `--output-root`，或先手动移走之前的输出。不要把个人设置、日志或截图放进构建目录。

## 分发内容

```text
ReelKeeper/
  ReelKeeper.exe
  _internal/          Python、Tcl/Tk、图像处理与 CPU 推理运行库
    nte_ocr/          自身应用模块，与 EXE 一起进入 app 组件
    licenses/         随附依赖的完整许可及第三方通知
  models/            两个 Tiny 模型及其 licenses/
  LICENSE
  THIRD_PARTY_NOTICES.md
  使用说明.txt
```

用户应完整解压到可写目录，不要单独移动 EXE。运行产生的 `settings.json` 和 `logs/` 位于 EXE 旁，更新时保留；便携包不携带开发者的个人设置或日志。

构建采用 PyInstaller onedir，不使用 UPX。精确排除 RapidOCR 未使用的三项内置权重、OpenCV FFmpeg 视频库及未支持的 AVIF / WebP 编解码器。截图试算仍支持 PNG、JPEG、BMP。

## 节省服务器流量

首次安装推荐 7z 全量包，ZIP 作为通用解压格式的备选。不要让用户先下载全量包再额外下载一遍组件。

`components.json` 列出三个 ZIP 组件的文件名、字节数和 SHA-256：

- **app**：EXE、自身模块和顶层说明。仅修改程序且引擎与模型匹配时，可只分发此组件；需要覆盖 EXE 和 `_internal/nte_ocr/`，不能只替换 EXE。
- **engine**：除自身模块外的 `_internal/`，包括对应的许可。
- **models**：Tiny 权重和模型许可。

同一次构建的三个组件可解压到同一目录组装完整程序。跨版本更新必须由发布者核对引擎、模型是否匹配；若变化或不能确认，提供新的全量包。清单只是供发布与核对使用，程序不会据此自动联网更新。

ZIP 时间戳固定，文件按路径排序，避免仅因构建时的压缩时间戳变化就让相同载荷的下载校验值变化。依赖、Python 版本、构建器与原生资源仍应保持一致；不宣称跨环境构建必定逐字节相同。

## 验证成品

源码检查：

```powershell
.\.venv-build\Scripts\python.exe -m pip check
.\.venv-build\Scripts\python.exe -m unittest discover -s tests -v
```

从三个组件重建并运行真实 EXE，验证中文 / 空格路径、模型加载、配置保留与缺失模型错误：

```powershell
.\.venv-build\Scripts\python.exe tools/verify_portable.py dist/portable --work-directory 'C:\private\ReelKeeper 验证'
```

验证目录必须尚不存在。可加 `--fixtures 'C:\private\reelkeeper-fixtures'`，读取已有私有回归截图并比较识别与筛选结果；样本约定见 [测试说明](testing.md)。验证报告留在验证目录，不放入公开包。此过程不操作游戏、不投币。

用户也可进行安装自检：

```powershell
Start-Process -Wait -WindowStyle Hidden -FilePath '.\ReelKeeper.exe' -ArgumentList '--check-installation', 'check.json'
```

成功报告中 `ok` 为 `true`。模型缺失会报错，不自动另行下载。自检仅验证运行环境，不代表已经实机验证游戏输入或 Windows UAC 交互。

## 比较体积与发布

`--baseline` 构建保留闲置模型和视频库的普通归档，用于与裁剪后的包比较。`sizes.json` 分别记录未压缩目录、全量 ZIP、可选 7z 和组件体积；下载成本应比较实际归档字节数，不能把目录大小当下载大小。

发布前核对版本及 CHANGELOG，确认权重与运行库许可已保留、包内没有个人配置、日志、截图或凭据。源码包只导出 Git 跟踪的源码；不要直接压缩整个本机项目目录。敏感信息若曾进入 Git 历史，仅补 `.gitignore` 不会移除历史内容。

默认分支为 `main`，公开仓库为 [yuchen-ya/nte-reelkeeper](https://github.com/yuchen-ya/nte-reelkeeper)。首次 Release 只分发一个完整 7z 便携包；组件包是可选的维护者构建产物。构建脚本不会自动提交 Git 或发布 Release。

Windows CI 执行公开测试；未提供私有截图时会明确跳过两组回放 / OCR 测试，不能将 CI 通过描述成游戏实机验收。
