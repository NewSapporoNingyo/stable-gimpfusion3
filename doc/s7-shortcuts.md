# S7 快捷键生成

## 命令与菜单

`GimpFusion → Generate with current parameters` 对应固定 PDB 名称
`stable-gimpfusion-generate-current`，接收 GIMP 当前图像，使用面板中的模式与最新参数生成。
图像存在时可调用，文生图支持空白图像。

文生图、图生图和局部重绘的交互菜单打开同一个常驻面板，更新目标图像并切换到对应模式。
首次启动恢复上次参数，再应用菜单指定的模式；已有面板保留当前编辑的参数。
点击面板生成按钮或调用快捷键时提交任务。

三个原有过程的 `NONINTERACTIVE`、`WITH_LAST_VALS` 调用继续使用过程配置中的参数直接生成。

## 首次启动与临时命令

首次调用由图像菜单过程承载面板生命周期，异步连接 Forge，恢复保存的参数。
快捷键触发的首次生成在编辑器就绪后执行一次。启动期间重复生成返回 `CANCEL`。
后续调用通过 `stable-gimpfusion-panel-command` 交给现有面板。

| 参数 | 值与用途 |
| --- | --- |
| `action` | `present` 呈现面板；`set-target` 更新目标；`generate` 生成；`close` 关闭 |
| `image` | 调用方传入的目标图像；`set-target` 可清空目标 |
| `mode` | `current` 保持面板模式；`txt2img`、`img2img`、`inpaint` 切换到对应模式，默认 `current` |

按钮和快捷键共用面板生成流程。每次生成先读取最新来源，再确定参数、像素、选区、蒙版和目标图像的快照。
任务运行或面板关闭时，追加生成返回 `CANCEL`。参数和目标切换继续用于后续任务。
结果插入、进度、通知和关闭流程沿用 [S5 常驻生成窗口](s5-panel.md)。

## 快捷键设置

1. 打开 GIMP 的“编辑 → 键盘快捷键”。
2. 搜索 `stable-gimpfusion-generate-current` 或 `Generate with current parameters`。
3. 点击该命令的快捷键列，按 `Ctrl+Alt+G`，点击“保存”。
4. 在面板中设置参数，回到画布绘画，再按快捷键生成。

设置方法见 [GIMP 键盘快捷键对话框](https://docs.gimp.org/3.0/en/gimp-help-keyboard-shortcuts.html)。

## 实机验收

代码提交 `48450b1` 推送后，正式插件目录通过 `pull --ff-only` 更新。
在本机 GIMP 3.2.6、Python 3.14.7、GTK 3.24.52 中连接 Forge 验收。

| 场景 | 结果 |
| --- | --- |
| 新命令首次调用 | 从菜单启动面板，恢复 txt2img 参数并生成 seed 77001 的 512×512 图层 |
| 新命令调用已有面板 | 在画布新增笔画后调用菜单命令，沿用 inpaint 模式与 seed 77003，图层数从 2 增至 3 |
| 快捷键首次调用 | 面板关闭时按 `Ctrl+Alt+G`，恢复 txt2img、seed 77004、Euler、5 步、512×512，自动生成，图层数从 3 增至 4 |
| 快捷键调用已有面板 | 切换到 img2img、修改为蓝色房屋提示词，在来源图层新增红色笔画后按键；复用同一面板，图层数从 4 增至 5，结果保留新笔画，图层信息包含新提示词与 seed 77004 |
| 三种菜单首次启动 | 三个实际 PDB 过程以 `INTERACTIVE` 调用，分别打开 txt2img、img2img、inpaint 面板，均返回 `SUCCESS` |
| 首次启动的参数恢复 | 三种模式均保留 seed 77002 和蓝色房屋提示词，关闭后保存指定模式 |
| 三种菜单调用已有面板 | 均返回 `SUCCESS`，复用同一个窗口并更新目标图像与模式 |
| 文生图 | seed 77001，Euler、5 步、CFG 5，生成 512×512 图层，返回信息包含本次提示词 |
| 图生图 | 编辑面板提示词并在来源图层绘画后生成，结果插入原目标图像 |
| 局部重绘 | 当前选区覆盖 512×512 来源，seed 77003，返回信息包含蓝色房屋提示词、降噪强度 0.45 和 mask blur 4 |
| 单任务与目标切换 | 连续调用返回 `SUCCESS`、`CANCEL`；任务期间切换目标返回 `SUCCESS`，结果进入任务开始时的目标 |

`shortcutsrc` 已保存 `Ctrl+Alt+G`，菜单显示该组合键，首次调用与已有面板调用均完成真实 Forge 生成。
本机 Chrome 桌面快捷方式曾占用该全局热键，Windows 注册检查返回错误码 1409。
按用户选择清除 Chrome 快捷方式的全局热键后，注册检查成功，GIMP 接收到按键并完成上述两次生成。
TODO 的 S7 三项均已完成。

视觉检查使用全屏截图。独立快捷键对话框的自动输入会切回主窗口，绑定通过 GIMP 配置文件设置。
批处理验收与普通 GIMP 会话分别验证，临时验收脚本保存在系统临时目录。
验收结束后恢复用户原有面板参数，保留 `Ctrl+Alt+G` 绑定，关闭电脑操控会话并终止本次 Forge 实例。

## 检查

GIMP Python 运行 37 项单元测试，全部通过。修改的 4 个 Python 文件通过 Ruff 和 mypy。
en、it、ru 的新增文案已编译为 `.mo`，通过 gettext 加载并核对译文。

```powershell
& 'C:\Program Files\GIMP 3\bin\python.exe' -B -m unittest discover -s test
$s7PythonFiles = @(
    'stable-gimpfusion3.py', 'sg_plugins/panel.py',
    'sg_plugins/generation_base.py', 'test/test_panel.py'
)
.\.venv\Scripts\ruff.exe check @s7PythonFiles
.\.venv\Scripts\mypy.exe @s7PythonFiles
git diff --check
```
