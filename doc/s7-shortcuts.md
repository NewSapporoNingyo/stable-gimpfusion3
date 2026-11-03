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
