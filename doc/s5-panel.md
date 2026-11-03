# S5 常驻生成窗口

## 使用与窗口

从 GimpFusion 菜单选择“Open generation panel”，面板绑定当前图像。
窗口顶部提供目标图像、预设和生成模式，中部滚动显示来源、提示词、LoRA 和参数，底部保留进度、通知开关及生成、关闭按钮。
预设操作、LoRA 和 ControlNet 参数可以展开。

默认窗口为 480×800，最小尺寸为 360×480，单位为 GTK 逻辑像素。
面板由独立的 `Gtk.Window` 承载，可通过任务栏单独呈现，并出现在 Windows 分屏候选中。
将 GIMP 标题栏拖到屏幕一侧，再选择面板或拖动面板标题栏完成贴靠。

菜单过程为 `stable-gimpfusion-panel`，类型为 `PLUGIN` 的 `ImageProcedure`。
GIMP 将当前图像传给菜单过程；插件通过 `persistent_enable()` 接收临时 PDB 调用，并在窗口存续期间运行 GTK 主循环。
临时过程 `stable-gimpfusion-panel-command` 接受 `present`、`set-target`、`generate`、`close`，以及对应的 `image` 参数。
重复打开菜单会呈现现有窗口。任务运行时，临时生成调用返回 `CANCEL`。

## 输入与任务

点击生成时，主线程读取当前目标图像、来源像素、选区、蒙版、ControlNet 图层与生成参数，形成请求快照。
模型设置、生成、LoRA 刷新、进度和中断请求通过工作线程中的 ApiClient 执行。
工作完成后，通过 GLib 回到主线程更新界面和插入结果。

面板一次运行一个生成任务。进度每两秒读取一次，进度请求超时为五秒。
任务期间可以修改面板参数、切换目标图像或在 GIMP 中绘画。
本次结果使用任务开始时的输入和目标，尺寸、偏移、选区蒙版和生成信息沿用 S2–S4 的规则。
结果插入及属性设置构成一次撤销操作。

原目标图像关闭后，任务显示“Target image closed; task finished”。
生成期间关闭面板会中断 Forge，处理已返回的候选，随后结束插件进程并释放临时命令。

## 参数保存与通知

JSON 配置中的 `panel_state` 保存生成参数、LoRA、预设名称、窗口宽高和通知开关。
重开时恢复上次面板中的完整参数。首次打开时载入上次预设，随后采用默认值。
图像和图层引用属于当前 GIMP 会话，目标切换时刷新来源并清空 ControlNet 图层选择。

配置写入合并本次修改的字段，保留其他设置窗口已保存的内容。
每次生成准备时读取最新的全局配置，并固定到本次请求中。

Windows toast 默认开启，在生成成功且结果插入后发送一次。
中断、失败及目标已关闭的任务显示各自的结束状态。
通知使用本机 GIMP 的应用标识，由隐藏的 Windows PowerShell 进程调用 WinRT；发送错误显示在面板状态区。

## 实机验收

验收环境为本机 GIMP 3.2.6、Python 3.14.7、GTK 3.24.52、PyGObject 3.58.0，连接本机 Forge。
开发副本使用隔离的 GIMP 配置验证，界面通过全屏截图核对。

| 场景 | 结果 |
| --- | --- |
| 菜单绑定 | 普通图像过程传入当前图像，目标选择可切换输入 |
| 窗口独立性 | 独立顶层窗口，Windows 分屏候选显示 GimpFusion 面板 |
| 窄窗口 | 展开参数后在 360、480、860 宽度间调整；860 收回 360 后控件可访问，底部按钮可见 |
| 文生图，seed 75001 | 512×512，偏移 `(0, 0)` |
| 图生图，seed 75002 | 512×512，偏移 `(32, 24)` |
| 选区重绘，seed 75003 | Whole picture 返回 512×512，偏移 `(32, 24)` |
| 图层蒙版重绘，seed 75004 | Only masked 返回来源尺寸 512×384，偏移 `(32, 24)` |
| ControlNet 与 LoRA，seed 75005 | reference_only 生成成功，导入候选及辅助图层；启用 LoRA 权重 0.25，禁用条目保持配置 |
| 运行期间切换与绘画 | 任务继续执行，结果进入原目标；主线程可执行画笔操作 |
| 原目标关闭，seed 75007 | 显示目标关闭状态，完成任务清理 |
| 运行期间关闭，seed 75006 | Forge 的 interrupted 为 true、job_count 为 0；窗口关闭并保存 seed、步数及 360×480 尺寸 |
| Windows 通知 | WinRT 通知历史收到成功任务的完成通知 |

## 检查

使用 GIMP Python 运行 29 项 unittest，全部通过。
修改文件通过 Ruff、mypy、翻译格式与编译检查及 `git diff --check`。

```powershell
& 'C:\Program Files\GIMP 3\bin\python.exe' -B -m unittest discover -s test -v
.\.venv\Scripts\ruff.exe check stable-gimpfusion3.py sg_plugins/panel.py sg_plugins/generation_base.py sg_plugins/lora_selector.py sg_structures.py sg_constants.py sg_notifications.py sg_gtk_utils.py test/test_panel.py test/test_runtime.py
.\.venv\Scripts\mypy.exe stable-gimpfusion3.py sg_plugins/panel.py sg_plugins/generation_base.py sg_plugins/lora_selector.py sg_structures.py sg_constants.py sg_notifications.py sg_gtk_utils.py test/test_panel.py test/test_runtime.py
git diff --check
```
