# ReelKeeper

《异环》驱动块 OCR 筛选助手，自动完成：

**投币十连 → 快进 → 读取词条 → 锁定 / 标记丢弃 → 返回投币页 → 下一轮。**

## 下载使用

[下载 Windows x64 便携版](https://github.com/yuchen-ya/nte-reelkeeper/releases/latest)（约 53 MiB）

完整解压后双击 `ReelKeeper.exe`，无需安装 Python 或另行下载模型。保留旁边的 `_internal/` 和 `models/` 文件夹。

1. 打开游戏的高级难度倒带页面，确认工具选中了正确窗口。
2. 设置保留规则和轮数，按 **F8** 开始，**F9** 停止。
3. 游戏保持打开、未最小化；可从投币页、动画页或十连结果页接续。

支持只处理当前结果、预览和截图试算。自动循环每次十连消耗 600 游戏金币；丢弃只做标记，不分解物品。每轮结束都会返回投币页。

工具不会移动系统鼠标，游戏窗口可能短暂闪动。设置和日志保存在 EXE 旁，更新时保留 `settings.json` 和 `logs/`。

## 保留规则

只看**词条种类和组合**，不比较数值。固定攻击、生命、防御与对应百分比词条分别识别。

默认保留：

- 同时具有暴击率和暴击伤害。
- 暴击率、暴击伤害、伤害增加、攻击力百分比，四项中至少三项。

可以添加多组规则，设置必备词条与命中数量；满足任意一组就保留。识别不可靠或已有相反标记时停止，供人工核对。

## 从源码运行

需要 Windows x64 和标准 CPython 3.12（含 Tkinter）：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

源码版首次启动需要下载约 6 MB 的 OCR 模型，之后本地识别。

[测试说明](docs/testing.md) · [构建与分发](docs/releasing.md) · [参与开发](CONTRIBUTING.md)

## 许可与说明

原创代码采用 [MIT](LICENSE)，依赖和模型许可见 [第三方说明](THIRD_PARTY_NOTICES.md)。

本工具非官方，不修改游戏文件、不读取游戏内存、不注入进程。自动化操作可能违反游戏规则并带来账号风险，请自行确认规则。反馈截图或日志前，请移除 UID、昵称和个人路径。
