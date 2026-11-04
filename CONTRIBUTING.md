# 参与开发

使用 Windows、标准 CPython 3.12（带 Tkinter）和本项目虚拟环境。安装与启动见 README。

修改以当前真实需求和已知游戏界面为范围，优先复用标准库与现有依赖。输入失败应明确停止；不要悄悄切换为移动系统鼠标、连续重试投币或自动确认未知弹窗。

提交前执行：

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

涉及识别或循环推进时，还应使用自己的私有截图执行回放测试，方法见 [测试说明](docs/testing.md)。自动化测试不得对真实游戏发点击，也不得消耗游戏货币。

PR 请说明改变的行为、触发条件、验证结果及仍未验证的部分。涉及真实输入的修改，不要把单元测试通过描述为实机验证通过。

提交截图、日志或 Issue 前，移除账号 UID、昵称、聊天内容、桌面内容、个人文件路径及凭据。不要提交 `.venv/`、`models/`、`settings.json`、`logs/`、`work/` 或 `tests/fixtures/`。第三方代码或资源需要说明来源和许可证，不能直接套用本项目的 MIT。
