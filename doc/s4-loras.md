# S4 LoRA 选择器

## 界面与配置

三种生成模式共用 LoRA 选择器。搜索按名称与 alias 匹配，`Add LoRA` 添加当前选中的模型。
新条目默认启用，权重为 1。权重接受有限实数，支持负数和 0。
重复添加同一名称时，焦点移到已有条目的权重输入框。
每项提供启用开关、权重输入框和移除按钮；名称与 alias 不同时分别显示。
权重输入错误显示在对应条目，修正后恢复生成和预设保存。

`LoRA details` 显示当前候选模型的路径与 metadata。
`Final LoRA tags` 随提示词和选择器配置更新，显示最终请求中的标签。

命名预设中的 `loras` 保存有序列表，每项包含 `name`、`alias`、`weight`、`enabled`。
保存、另存为和载入共用现有预设流程。提示词字段保存用户输入的原文。

## Forge 接口与标签合成

打开生成窗口时，通过 ApiClient 请求 `GET /sdapi/v1/loras`。
`Refresh LoRAs` 按 `POST /sdapi/v1/refresh-loras` → `GET /sdapi/v1/loras` 刷新目录。
目录保存在当前生成过程内。刷新与载入预设保留已选条目的顺序、权重和开关。

本机 Forge 的 `/config` 中，`setting_lora_preferred_name` 提供引用偏好。
名称与 alias 的查找顺序、重复 alias 和引用名称遵循本机 `sd_forge_lora` 的
`process_network_files()`、`load_networks()` 和 `NetworkOnDisk.get_alias()`。

正向提示词先组合本次文本与公共后缀，再合成选择器条目：

- 启用条目以模型名称合并手写标签。第一次出现的位置采用选择器权重，其余同模型标签合并到该项。
- 新启用的模型按已选列表顺序追加，标签为 `<lora:标识:权重>`。
- 其余手写标签保留原文和顺序，重复标签与附加参数交给 Forge 解析。
- 禁用条目保留配置，手写标签继续参与请求。
- 缺失模型按保存的标识提交，模型加载由 Forge 处理。

界面预览、三种模式的请求和 PDB 非交互调用使用同一合成函数。
重复构建请求保持提示词原文与选择器配置。

## 验收

验收环境为本机 GIMP 3.2.6、Python 3.14.7、PyGObject 3.58.0、GTK 3.24.52、requests 2.34.2。
Forge 提供 15 个 LoRA，引用偏好为 `Alias from file`。

通过 computer-use 检查名称搜索、alias 搜索、添加、重复添加定位、启用开关、权重修改、移除与刷新。
输入 `abc` 时生成和保存按钮禁用；改为 `-0.5` 后恢复，预览显示相同权重。
禁用条目后，预览恢复提示词中的手写权重。详情中的路径与 metadata 显示正确。
图形检查使用全屏截图。

单元测试覆盖名称与 alias 合并、手写重复标签、附加参数、引用偏好、重复 alias、缺失模型、
负权重、零权重、输入解析及预设保存恢复。en、it、ru 各维护并编译 12 条 S4 文本。

开发副本使用 `waiIllustriousSDXL_v170.safetensors`、Euler、5 步、CFG 5 完成真实生成：

| 模式 | seed | 请求与结果图层尺寸 | 图层偏移 |
| --- | --- | --- | --- |
| 文生图 | 74001 | 512×512 | `(0,0)` |
| 图生图 | 74002 | 512×512 | `(32,24)` |
| 选区局部重绘，Whole picture | 74003 | 512×512 | `(32,24)` |

三次请求启用 `deepseek_maid_outfit_illustrious_v10`（权重 0.25）、`lineweight_slider`（-0.35）
和 `il_brightness_slider_d1`（0）；`sketch_slider` 保存为禁用状态。
第一个模型使用 alias `deepseek_maid_outfit_illustrious_v02_visibility_r16_s900`。
Forge 的响应参数与提交的 prompt 一致，infotext 包含三个已加载模型的 hash。
提示词中的名称和 alias 两种写法、公共后缀中的重复标签按选择器权重合成。
生成后提示词原文和选择器配置保持原值，结果图层的 seed 与请求相同。

两套预设分别保存文生图与局部重绘配置，载入和保存后，条目顺序、权重、启用状态及界面输入一致。

检查命令：

```powershell
& 'C:\Program Files\GIMP 3\bin\python.exe' -B -m unittest discover -s test -v
.\.venv\Scripts\ruff.exe check sg_loras.py sg_plugins/lora_selector.py sg_generation.py sg_plugins/generation_base.py sg_utils.py test/test_loras.py test/test_presets.py
.\.venv\Scripts\mypy.exe sg_loras.py sg_plugins/lora_selector.py sg_generation.py sg_plugins/generation_base.py sg_utils.py test/test_loras.py test/test_presets.py
& 'C:\Program Files\Git\bin\bash.exe' -n update-translations.sh
git diff --check
```

12 项 unittest、修改文件的 Ruff 和 mypy、翻译格式与加载检查、脚本语法和差异空白检查通过。

## 安装副本验收

代码提交 `43eb937` 推送后，安装副本通过 `pull --ff-only` 更新。
重启 GIMP，从 GimpFusion 菜单打开文生图，预设 A 自动恢复四个条目、权重、开关、原始提示词和 seed 74011。
点击生成后插入对应结果图层。

再次重启 GIMP，通过安装副本的局部重绘过程打开预设 B，恢复三个条目的顺序与配置：
`sketch_slider` 为 0.4 并启用，deepseek 模型为 0.1 并禁用，brightness 为 0 并启用。
预览保留手写的 `lineweight_slider` 标签 0.6 和公共后缀中的 0.1，点击生成后完成局部重绘。

安装副本三个实际注册的 PDB 过程均返回 `SUCCESS`：

| 过程 | 预设 | seed | 结果图层尺寸 | 图层偏移 |
| --- | --- | --- | --- | --- |
| `stable-gimpfusion-txt2img` | A | 74011 | 512×512 | `(0,0)` |
| `stable-gimpfusion-img2img` | A | 74013 | 512×512 | `(32,24)` |
| `stable-gimpfusion-inpainting` | B | 74012 | 512×512 | `(32,24)` |

结果图层保存的 infotext 与合成后的提示词一致，seed 与请求相同。
实际菜单、预设恢复和图层结果通过全屏截图核对。
验收结束后恢复原有公共提示词和上次预设，清理两套验收预设与临时文件，终止本次 Forge 服务。

S4 三项待办均已完成。
