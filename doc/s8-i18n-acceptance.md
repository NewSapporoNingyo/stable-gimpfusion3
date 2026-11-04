# S8 翻译、同步与验收

## 翻译与说明

en、it、ru、zhcn 四种语言均覆盖当前 178 条消息，包含菜单、参数、帮助、状态、通知、错误和结果图层名称。
修复俄文目录中的问号乱码，补齐英文和俄文漏译。API 字段、模型、采样器和技术选项保留原文。

GIMP 插件进程使用 `zh_CN` 标识简体中文。Python 加载器将该标识映射到 `zhcn`；中文译文维护在 `zhcn`，
翻译脚本生成同内容的 `zh_CN` 二进制目录供原生菜单加载。入口采用 GIMP 默认的 domain 与目录规则。

按 S1 调研和本机 Forge 源码修订采样、CFG、降噪、蒙版模糊、平铺、尺寸插入、重绘区域和填充方式说明。
ControlNet 参数说明覆盖预处理器、模型、权重、起止进度、分辨率和阈值。
“只导入生成候选”写清两个开关状态的导入结果及三种模式的适用范围。

英文 [README](../README.md) 和[简体中文 README](../README.zh-CN.md)完整说明安装、配置文件、手动 XCF 数据、
来源、蒙版、LoRA、ControlNet、常驻面板、Windows 分屏和快捷键操作。

## 静态检查

使用 GIMP Python 3.14.7 运行 39 项 unittest，全部通过。6 个修改的 Python 文件通过 Ruff 和 mypy。
四种译文均通过 `msgcmp` 和 `msgfmt --check --check-format`，有效词条零未译、零模糊译文。
中文两个 `.mo` 文件内容一致。翻译脚本语法和差异空白检查通过。

```powershell
$s8Files = @(
    'sg_i18n.py', 'sg_proc_arguments.py', 'sg_structures.py',
    'sg_gtk_utils.py', 'stable-gimpfusion3.py', 'test/test_i18n.py'
)
.\.venv\Scripts\ruff.exe check @s8Files
.\.venv\Scripts\mypy.exe @s8Files
& 'C:\Program Files\GIMP 3\bin\python.exe' -B -m unittest discover -s test
& 'C:\Program Files\Git\bin\bash.exe' update-translations.sh
& 'C:\Program Files\Git\bin\bash.exe' -n update-translations.sh
git diff --check
```

## 安装副本与实机结果

实现提交 `e6fe036`、意大利文窄窗口标签修正 `ba56918` 已推送，正式插件目录通过 `pull --ff-only` 更新。
使用本机 GIMP 3.2.6、Python 3.14.7、GTK 3.24.52 与 Forge，在隔离的 GIMP 配置中加载正式安装目录的代码。

| 场景 | 实测结果 |
| --- | --- |
| 四种语言 | 各自的 GIMP 会话加载已译菜单、面板标题和参数帮助；360 宽窗口中控件可访问 |
| 中文显示 | 来源、提示词、生成状态、结果图层名称及目标关闭消息显示中文 |
| 两套配置文件 | 中文、多行、百分号与 LoRA 标签完整保存；两套文件分别在三种模式下恢复提示词和 seed，并完成回存 |
| XCF | 手动保存生成数据，XCF 保存重开后 Parasite 的 1082 字节内容一致，手动载入恢复参数 |
| 文生图，78011 | 请求 512×512，按默认选区插入策略得到 640×576 图层，偏移 `(0, 0)` |
| 图生图，78012 | 512×512 图层，偏移 `(32, 24)` |
| 选区重绘，78013 | Whole picture 返回 512×512 图层，偏移 `(32, 24)` |
| 图层蒙版重绘，78014 | Only masked 返回来源尺寸 512×384，偏移 `(32, 24)` |
| ControlNet | reference_only 返回候选与参考图；开关开启导入 1 层，关闭导入 2 层 |
| 来源编辑与目标切换 | 修改来源像素后生成；忙碌期间追加任务被拒绝，切换目标后结果进入原目标 |
| 目标关闭 | 任务期间关闭目标后显示“目标图像已关闭；任务结束” |
| 关闭与重开 | 保存 seed 78019 和 360×600 尺寸，重开编辑器读取到相同参数与尺寸 |
| 快捷键首次启动 | 正常用户配置下按 Ctrl+Alt+G，正式菜单过程启动面板并生成 seed 78021，图层数从 1 增至 2 |
| 编辑后再次生成 | 用 GIMP 画笔过程修改来源，再按 Ctrl+Alt+G；复用已有面板，图层数从 2 增至 3，seed 保持 78021 |
| 撤销与继续修图 | 一次 Ctrl+Z 将图层数从 3 恢复为 2，随后继续使用画笔编辑 |
| Windows 分屏 | 用户完成 GIMP 与面板贴靠并确认布局正常；全屏截图核对来源预览、文字和底部生成按钮 |

视觉检查使用全屏截图；窗口截图接口返回超时，坐标输入返回 `coordinate input geometry is unavailable`。
分屏拖动由用户完成，快捷键由电脑操控接口执行。意大利文模式标签在窄窗口检查后缩短为 `Modalità`，并复核编译和加载。

正常用户配置下的快捷键与绘画流程加载正式安装目录的插件；验收结束后关闭面板及验收 GIMP 实例，恢复原有插件参数。
电脑操控会话已关闭，本次 Forge 实例已终止。验收脚本和生成资料保存在系统临时目录。
