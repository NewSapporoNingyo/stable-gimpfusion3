# S2 命名预设

## 配置与操作

`stable_gimpfusion.json` 的 `presets` 以名称为键，保存完整生成参数；`last_preset` 保存上次载入或保存的名称。
现有连接设置、全局提示词后缀和其他设置保留在原位置。配置使用 UTF-8。

| 操作 | 结果 |
| --- | --- |
| 载入 | 恢复模式及完整参数，更新 `last_preset` |
| 保存 | 将当前参数写入正在编辑的命名预设 |
| 另存为 | 去除名称首尾空白，创建新名称；空名称和重名在输入框中提示 |
| 删除 | 删除列表选中的预设，保留窗口参数；删除上次预设时清空 `last_preset` |

三个原有菜单打开同一套生成界面，分别提供初始模式。同模式的上次预设自动恢复；跨模式预设通过“载入”切换。
载入时先检查完整字段、参数范围及 Forge 标识，再更新窗口。列表选择与正在编辑的预设分别记录，“保存”作用于正在编辑的预设。

每套预设包含公共参数和所有现有模式参数、checkpoint、两组 ControlNet 参数及辅助图层显示选项。
模型、采样器、处理器和 ControlNet 模型保存字符串标识。来源图层、ControlNet 输入图层和像素数据由当前文档提供。
`loras` 列表保存 `name`、`alias`、`weight`、`enabled`，在保存和载入时保留。当前通过提示词中的手写标签使用 LoRA。

## 参数与请求

- 正向、负向提示词均按“本次提示词 + 一个空格 + 全局后缀”合成，最后去除首尾空白。
- seed 范围为 `-1` 至 `4294967295`。`-1` 表示随机，非负整数表示指定种子。PDB 使用 double，JSON 和 Forge 请求使用整数。
- 三个 PDB 过程名称沿用现有名称，新增 `generation_mode` 等共用参数；非交互调用使用传入参数。
- 文生图显示适用参数，请求中使用 `enable_hr=false`。降噪强度由图生图和局部重绘使用。
- 文生图、图生图和局部重绘采用界面宽高。文生图的 `Use selection size` 采用选区尺寸，取最近的 8 倍数。
- 宽高范围为 64–2048，滑块单步为 8。手动输入的宽高须为 8 的倍数；非法值保留在界面中，修正后恢复生成、保存和另存为。按选区尺寸生成时，生成按钮按选区的实际请求尺寸启用。
- 旧预设按原值载入，宽高修正后通过保存更新预设。窗口显示实际请求尺寸和按插入策略计算的结果尺寸；局部重绘显示来源尺寸。
- 每次生成先通过 ApiClient 提交 checkpoint 设置，再提交生成请求。
- 两组 ControlNet 参数由预设提供，输入像素来自当前选中的对应图层，使用 Forge 的 `image` 和 `mask_image` 字段。
- `Read layer settings` 从所选图层读取可复用参数。图层配置过程直接保存处理器和模型的字符串标识。

## 开发副本验收

在本机 GIMP 3.2.6、Python 3.14.7、GTK 3.24.52、requests 2.34.2 中执行，连接本机 Forge。
模型为 `waiIllustriousSDXL_v170.safetensors`，采样器为 Euler，步数为 5。

| 流程 | 请求尺寸 | seed | 结果图层尺寸 |
| --- | --- | --- | --- |
| 文生图 | 512×512；界面宽高 513、516 | 0 | 384×256 |
| 图生图，ControlNet 1 Reference | 384×256 | 70000 | 384×256 |
| 选区重绘，ControlNet 2 Reference | 512×512 | 4294967295 | 384×256 |
| 图层蒙版重绘，全分辨率模式 | 512×512 | 123456789 | 640×512 |

ControlNet 两组分别使用 `reference_only`，权重为 0.6、0.4。请求记录确认模型设置先于生成请求。
Forge 返回的 seed 与图层 `gimpfusion` Parasite 一致。

预设操作验收覆盖中文名称、保存、另存为、删除、名称去空白、空名称、重名，以及失效采样器。
失效预设在更新窗口前报告错误，当前参数保持原值。删除后保留当前参数。

关闭并重新启动 GIMP 宿主后，分别载入 `S2 文生图` 和 `S2 重绘` 并生成，seed 分别恢复为 0 和 4294967295。
三个入口的初始模式、同模式自动恢复及跨模式显式载入均通过。另以 seed `-1` 生成，实际返回 seed 290467547。

检查命令：

```powershell
$s2Files = @(
    'stable-gimpfusion3.py', 'sg_generation.py', 'sg_structures.py', 'sg_proc_arguments.py', 'sg_utils.py',
    'sg_plugins/__init__.py', 'sg_plugins/generation_base.py', 'sg_plugins/config_controlnet.py',
    'sg_plugins/txt2img.py', 'sg_plugins/img2img.py', 'sg_plugins/inpainting.py', 'test/test_presets.py'
)
& 'C:\Program Files\GIMP 3\bin\python.exe' -B -m unittest discover -s test -v
.\.venv\Scripts\ruff.exe check @s2Files
.\.venv\Scripts\mypy.exe @s2Files
& 'C:\Program Files\Git\bin\bash.exe' -n update-translations.sh
git diff --check
```

四项 unittest 通过。Ruff、mypy 和翻译脚本语法检查通过。
en、it、ru 各增加并编译 22 条 S2 翻译，核对新增译文与格式占位符。

## 安装副本验收

开发副本提交并推送后，GIMP 插件副本通过 `pull --ff-only` 更新。入口文件随过程注册代码一同更新，使 GIMP 重新读取共用参数签名。

重启 GIMP 后，通过安装副本注册的 `stable-gimpfusion-txt2img` 和 `stable-gimpfusion-inpainting` 执行两套预设，均返回 `SUCCESS`。
`S2 文生图` 恢复 seed 0，`S2 重绘` 恢复 seed 4294967295，结果图层均为 384×256。
三个注册入口的初始模式分别为 txt2img、img2img、inpaint。

通过正常入口 `gimp-3.exe` 打开验收 XCF，确认 GimpFusion 的三个生成菜单均已加载。
从文生图菜单打开窗口后自动恢复同模式预设；在界面载入 `S2 重绘`，模式切换为 inpaint，提示词与 seed 4294967295 正确恢复。
使用 computer-use 操作，并按本机设备要求通过全屏截图检查控件和滚动区域。

安装副本配置中保留上述两套验收预设。
验收结束后已终止本次启动的 Forge 服务。
