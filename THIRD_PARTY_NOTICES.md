# 第三方依赖与来源

本项目原创代码使用 MIT 许可证。第三方库、模型、游戏名称及游戏图像的权利不因本项目的 MIT 许可证而转移。

## 运行依赖

源码发布包仅包含依赖声明，不包含虚拟环境、第三方 wheel、DLL 或模型权重。依赖由 pip 从各自的发布渠道安装；各发行包内的完整许可与通知继续适用。

Windows 便携包由 PyInstaller 6.22.3 构建，携带所需运行库；其完整许可与第三方通知位于 `_internal/licenses/`，模型许可位于 `models/licenses/`。PyInstaller bootloader 的许可证含分发例外，不将本项目原创代码改为 GPL。源码构建脚本另见 `requirements-build.txt`。

| 依赖 | 用途 | 上游许可 / 来源 |
| --- | --- | --- |
| RapidOCR 3.10.0 | OCR 检测与识别 | [Apache-2.0](https://github.com/RapidAI/RapidOCR/blob/v3.10.0/LICENSE) |
| ONNX Runtime 1.31.1 | CPU 推理 | [MIT](https://github.com/microsoft/onnxruntime/blob/main/LICENSE) |
| windows-capture 2.0.1 | Windows Graphics Capture | [MIT](https://github.com/NiiightmareXD/windows-capture/blob/main/windows-capture-python/LICENCE) |
| Pillow 13.0.0 | RapidOCR 图像处理依赖 | [MIT-CMU](https://github.com/python-pillow/Pillow/blob/main/LICENSE) |
| NumPy 2.5.4 | 图像数组计算 | [NumPy 许可证及随附第三方通知](https://github.com/numpy/numpy/blob/main/LICENSE.txt) |
| OpenCV Python 5.0.0.93 | 图像识别与处理 | [OpenCV / Python 打包许可](https://github.com/opencv/opencv-python/blob/master/LICENSE.txt) |

RapidOCR 还会安装 opencv-python-headless；windows-capture 依赖 opencv-python。两者均提供 cv2，当前组合已在 Windows CPython 3.12 验证。不要在工作环境中单独卸载其中一个包后继续运行；需要重建时重新运行安装脚本。

## OCR 模型

源码版由 RapidOCR 从 [RapidAI 模型库](https://modelscope.cn/models/RapidAI/RapidOCR)下载 PP-OCRv6 Tiny 检测及识别模型，保存在被 Git 排除的 `models/`。便携版原样携带这两个模型，明确从本地加载；缺失时停止并提示完整解压，不自动额外下载。

模型是独立的受许可作品，不适用本项目的 MIT 许可证。来源与权利说明见源码的 `packaging/model-notice.md`（便携包的 `models/licenses/NOTICE.md`）、[RapidOCR 模型许可说明](https://github.com/RapidAI/RapidOCR/blob/v3.10.0/python/MODEL_LICENSES.md)及 [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR)。Tiny 的官方模型卡声明 Apache-2.0；便携包随附完整 Apache 许可证、来源及转换说明，不改变权重。源码包仍不携带模型权重。

## 技术参考与游戏素材

窗口移位模拟点击的思路参考 [MaaFramework 的 WithWindowPos 控制方式说明](https://maafw.com/docs/2.4-ControlMethods/)。本项目不链接、打包 MaaFramework，也未复制其实现代码。

快进识别模板由程序绘制通用几何图形生成。公开源码不包含游戏截图、账号 UID、游戏资源文件或游戏客户端组件。

《异环》/ Neverness to Everness 及相关名称、商标和画面属于相应权利人。本项目是独立的第三方工具，与游戏官方没有隶属或合作关系。
