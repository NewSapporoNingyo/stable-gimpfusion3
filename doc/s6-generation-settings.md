# S6 细节修正与生成配置

## 提示词与 LoRA

正向、负向提示词输入区均为八行，高度按当前字体的行高计算，长文本通过滚动查看。
三种模式和常驻面板共用这两个输入区。

LoRA 列表支持名称与 alias 搜索、刷新及模型详情。单击模型后，将标签加入正向提示词；
再次点击时，按本机 Forge `updatePromptArea` 的匹配规则移除标签。
标签中的权重直接编辑，例如 `<lora:lineweight_slider:0.25>`。
引用名称、默认权重和分隔符读取 Forge 配置，提示词中的标签直接进入生成请求。

局部重绘的新建默认值为 `original`，对应 Forge API 的 `inpainting_fill=1`。
配置文件和图像附加数据中的显式填充选项按保存值恢复。

## 独立配置文件

展开 `Generation settings` 后使用以下操作：

| 按钮 | 操作 |
| --- | --- |
| Load file | 通过 Windows 系统文件对话框载入配置 |
| Save file | 保存到当前文件；首次保存时选择路径 |
| Save file as | 选择新路径并保存，后续保存使用新文件 |
| Save to image | 将当前配置附加到目标图像 |
| Load from image | 从目标图像的附加数据载入配置 |

当前文件名称显示在面板顶部，鼠标提示显示完整路径。
文件对话框使用 `Gtk.FileChooserNative`，文件类型为 `*.txt`；另存为从当前文件所在目录打开，
系统对话框处理覆盖确认。

文件采用 UTF-8 和 Windows INI 的节、键值结构，包含 `[generation]` 节和完整的 44 个生成字段。
字段名沿用 API 与插件参数名称，包含模型、正负提示词、通用参数、各模式参数和两组 ControlNet 配置。
ControlNet 输入图层由当前图像中的选择提供。

提示词字段使用 JSON 字符串保存换行、引号和空白，其余字段使用 INI 标量。以下展示部分字段：

```ini
[generation]
generation_mode = inpaint
prompt = "山间湖泊\n<lora:lineweight_slider:0.25>"
negative_prompt = "blurry, text"
seed = -1
width = 512
height = 512
denoising_strength = 0.55
inpainting_fill = original
```

INI 插值关闭，提示词中的 `%` 按原文保存。载入入口检查字段类型、数值范围、尺寸和本机可用选项，
解析或文件读写错误显示在面板中。

载入时保持当前模式，并应用提示词、模型和通用参数。各模式参数按下表应用：

| 模式 | 模式参数 |
| --- | --- |
| txt2img | 插入方式 |
| img2img | 降噪强度、缩放方式、蒙版模糊 |
| inpaint | 图生图参数，以及填充方式、重绘区域、padding、蒙版反转 |

其余模式参数保留在当前配置中，切换到相应模式时应用，保存文件时完整写入。
窗口关闭后，面板会话保存当前参数、文件路径、窗口宽高和通知开关；重开时恢复这些内容。

## XCF 中的配置

点击 `Save to image` 将同一份 INI 数据写入当前目标图像的
`stable-gimpfusion-generation` Parasite，标志为 `PERSISTENT | UNDOABLE`。
随后按 GIMP 的正常流程保存 XCF。重新打开 XCF 后，点击 `Load from image` 恢复参数。
这两个按钮负责图像附加数据的读写。

从图像载入后，面板显示该图像名称。将这套参数保存为独立文件时，通过系统对话框选择路径。
Parasite 写入参与 GIMP 撤销，文件和图像使用同一套解析与参数应用规则。

## 本机验收

环境为 GIMP 3.2.6、Python 3.14.7、GTK 3.24.52、PyGObject 3.58.0，连接本机 Forge。
开发副本通过隔离的 GIMP 配置运行，临时图像和配置保存在系统临时目录。

| 场景 | 结果 |
| --- | --- |
| 八行输入区 | 两个可编辑提示词框的最小内容高度均为八倍字体行高；实测行高为 17 |
| 窄窗口 | 宽度为 360，展开配置和 LoRA 后控件可用，底部操作可见 |
| LoRA | 列表启用单击激活；标签从 0.25 移除后重新加入为 Forge 默认权重 1 |
| 提示词往返 | 中文、多行、空白、引号、百分号及类似 INI 节和注释的文本完整恢复 |
| 输入解析 | 非八倍数尺寸、小数 seed、无限数值和无效选项在入口报错 |
| 三模式载入 | 保持当前模式；降噪强度在切换到图生图后应用；其余模式参数参与回存 |
| 文件按钮 | 保存当前文件、另存为和载入按钮回调完成实际文件读写 |
| Windows 原生对话框 | Save 和 Open 由用户点击，脚本核对载入参数及 seed 76005 的回存结果 |
| XCF 重开 | 保存并重开后 Parasite 数据相同，手动载入恢复提示词和参数 |
| 图像切换 | 两个图像间切换后，手动载入采用当前目标的附加数据 |
| Parasite 撤销 | GIMP 中一次 Ctrl+Z 将附加数据的 seed 从 76004 恢复为 76003 |
| 面板重开 | 恢复 seed 76004、当前文件路径、窗口尺寸和通知关闭状态 |
| 重绘默认值 | 新建配置选择 original，文件中的显式值正常恢复 |

同一套文件参数通过常驻面板完成真实生成，模型为 `waiIllustriousSDXL_v170.safetensors`，
Euler、5 步、CFG 5，提示词包含 `<lora:lineweight_slider:0.25>`：

| 模式 | seed | 结果尺寸 | 图层偏移 |
| --- | --- | --- | --- |
| txt2img | 76001 | 512×512 | `(0, 0)` |
| img2img | 76002 | 512×512 | `(32, 24)` |
| inpaint，Whole picture | 76003 | 512×512 | `(32, 24)` |

三次返回的图层信息均包含本次 seed 和提交的 LoRA 标签。
视觉检查使用全屏截图。窗口截图工具返回超时，原生模态框的输入定位失败；
原生保存、载入由用户完成点击，其余界面回调、数据核对和生成由验收脚本执行。

## 检查

GIMP Python 运行 31 项 unittest，全部通过。修改的 14 个 Python 文件通过 Ruff 和 mypy。
en、it、ru 的 S6 文案已更新并编译，翻译格式、脚本语法和差异空白检查通过。

```powershell
& 'C:\Program Files\GIMP 3\bin\python.exe' -B -m unittest discover -s test
$s6PythonFiles = @(
    'sg_generation.py', 'sg_loras.py', 'sg_plugins/lora_selector.py',
    'sg_plugins/generation_base.py', 'sg_plugins/panel.py', 'sg_gtk_utils.py',
    'sg_proc_arguments.py', 'sg_constants.py', 'sg_utils.py', 'sg_structures.py',
    'test/test_generation_settings.py', 'test/test_loras.py', 'test/test_runtime.py', 'test/test_panel.py'
)
.\.venv\Scripts\ruff.exe check @s6PythonFiles
.\.venv\Scripts\mypy.exe @s6PythonFiles
& 'C:\Program Files\Git\bin\bash.exe' -n update-translations.sh
git diff --check
```
