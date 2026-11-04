# 测试说明

## 无私有素材的测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

验证保留词条组合、不同数值不影响同类词条判定、固定值与百分比分类、必备条件、配置迁移、界面状态、截图裁剪、Win32 输入边界和窗口还原。所有窗口输入均被模拟，不操作真实游戏。

没有私有截图时，两组截图 / 回放测试明确显示 `skipped`，不是截图识别已通过。此路径不创建 Reader、不下载 OCR 模型。Windows CI 执行这组测试。

## 私有截图与循环回放

游戏截图可能包含账号 UID，也涉及游戏画面权利，因此不放入公开仓库。可使用仓库外的私有目录：

```powershell
$env:REELKEEPER_TEST_FIXTURES = 'C:\private\reelkeeper-fixtures'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
Remove-Item Env:REELKEEPER_TEST_FIXTURES
```

也可放在被 Git 排除的 `tests/fixtures/`。显式配置的目录不存在或样本不完整时，测试会报错，不会按“未提供”跳过。

既有回归样本的契约：

| 文件 | 内容 |
| --- | --- |
| `menu.png` | 996 像素宽的高级难度投币页，十连按钮约位于 (690, 450) |
| `menu_live.png` | 实际窗口投币页，十连按钮位于 x=850～1000、y=550～630 |
| `animation.png` | 可见右上角快进图标的动画页 |
| `result_a.png` | 首件选中；副属性为固定攻击、伤害增加、百分比攻击、固定防御；未标记 |
| `result_b.png` | 第六件选中；暴击伤害、百分比防御、百分比攻击、百分比生命；已标记丢弃 |
| `detail_a.png` | 四条副属性的完整详情，默认规则应保留 |
| `detail_b.png` | 四条副属性的完整详情，默认规则不保留 |
| `detail_tilt.png` | 包含倾陷强度的详情，默认规则不保留 |

这些是既有测试的特定样本约定，任意游戏截图不能直接替换。添加其他截图时需要同步补充其预期结果和布局断言。不要发布未经脱敏、未经确认有权再分发的素材。

回放使用真实 OCR 和页面识别，但把点击发送给内存中的回放窗口，用于验证连续两轮、过渡画面接续、滞后动画帧、标记确认及返回投币页。它不等同于游戏版本更新后的实机验收。
