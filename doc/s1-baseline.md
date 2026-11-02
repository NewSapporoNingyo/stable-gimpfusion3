# S1 本机环境与运行基线

## 环境

本次验收在本机 GIMP 3.2.6 中执行。版本信息由 `python-fu-eval` 在 GIMP 插件进程内读取。

| 项目 | 实际值 |
| --- | --- |
| GIMP | 3.2.6 |
| `sys.version` | 3.14.7，MINGW Clang UCRT，64 位 |
| `sys.executable` | `C:\Program Files\GIMP 3\bin\python.exe` |
| PyGObject | 3.58.0 |
| GTK | 3.24.52 |
| Gimp / GimpUi GI 命名空间 | 3.0 / 3.0，均可导入 |
| requests | 2.34.2，可在 GIMP 插件进程内导入 |
| Forge 启动入口 | `C:\data\webui_forge_dev\run-forge.bat` |
| Forge 地址 | `http://127.0.0.1:7860` |
| Forge 启动参数 | `--api --cuda-malloc`，API 返回 `api=true`、`cuda_malloc=true` |
| 当前模型 | `waiIllustriousSDXL_v170.safetensors`，SDXL |
| Forge 推理环境 | Python 3.10.6、PyTorch 2.4.1+cu124、RTX 3060 12 GB |

后续插件开发以 Python 3.14 和本机自带的 GI 库为基准。`pyproject.toml` 和 `pdm.lock` 中的 Python 3.11、PyGObject 3.42.2 是上游环境记录。

初次检查时 GIMP Python 缺少 requests。依赖已安装到其启用的用户包目录：

```text
C:\Users\LHR\.local\lib\python3.14-mingw_x86_64_ucrt_llvm\site-packages
```

安装命令使用系统 pip 的 `--python` 参数指定 GIMP 解释器，`--target` 指定上述目录：

```powershell
python -m pip --python 'C:\Program Files\GIMP 3\bin\python.exe' install `
    --target 'C:\Users\LHR\.local\lib\python3.14-mingw_x86_64_ucrt_llvm\site-packages' `
    --only-binary=:all: requests
```

该调用方式见 [pip 的解释器选择说明](https://pip.pypa.io/en/stable/topics/python-option/)。

## Forge 接口约定

通过项目的 [ApiClient](../sg_structures.py) 请求服务。`GET /docs` 提供 Swagger 界面，`GET /openapi.json` 提供该实例的接口结构。

| 方法与路径 | 实际结果与用途 |
| --- | --- |
| `POST /sdapi/v1/txt2img` | 文生图成功；返回 `images`、`parameters` 和 JSON 字符串 `info` |
| `POST /sdapi/v1/img2img` | 图生图和两种蒙版局部重绘成功；蒙版由 `mask` 字段提供 |
| `GET /sdapi/v1/options` | 返回当前 `sd_model_checkpoint` 等服务设置 |
| `GET /sdapi/v1/sd-models` | 1 个 checkpoint；字段为 `title`、`model_name`、`hash`、`sha256`、`filename`、`config` |
| `GET /sdapi/v1/sd-modules` | 返回空列表；当前 SDXL 模型的附加模块列表为空 |
| `GET /sdapi/v1/loras` | 15 个 LoRA；每项包含 `name`、`alias`、`path`、`metadata` |
| `POST /sdapi/v1/refresh-loras` | 成功，响应 JSON 为 `null`；随后重新获取 LoRA 列表 |
| `GET /controlnet/model_list` | `{"model_list": ["None"]}` |
| `GET /controlnet/module_list` | 64 个预处理器，字段为 `module_list` |
| `GET /controlnet/control_types` | 按控制类型提供预处理器、模型及默认项 |
| `POST /controlnet/detect` | canny 预处理成功，返回 `info="Success"` 和 1 张检测图 |
| `GET /sdapi/v1/scripts` | txt2img 和 img2img 均包含 `controlnet` |
| `GET /sdapi/v1/script-info` | 提供 always-on 脚本的参数结构 |

S4 的 LoRA 选择器使用 `name` 作为稳定标识，保存 `alias` 供提示词标签使用，`path` 和 `metadata` 用于展示。刷新顺序为 `POST /sdapi/v1/refresh-loras` → `GET /sdapi/v1/loras`。本机存在 `name` 与 `alias` 不同的条目，两个字段分别保存。

ControlNet 随生成请求放入 `alwayson_scripts.controlnet.args`。本机 Forge 的 `ControlNetUnit` 使用 `image` 和 `mask_image` 字段；预处理器和模型标识按服务返回的原文传递，包括 `None` 的大小写。Reference 预处理器自带控制逻辑，本次使用 `reference_only`、`model="None"` 完成三种模式的辅助图验证。

## 四种生成流程的实测结果

使用专门创建的测试图像，通过 GIMP 内的生成过程执行。图生图修正后，另在 GIMP 插件进程中载入开发目录的同一模块执行。共同参数：

```text
prompt = a red ceramic teapot on a wooden table, still life
negative_prompt = text, watermark
sampler = Euler
steps = 5
cfg_scale = 5
denoising_strength = 0.6（图生图与局部重绘）
```

表中“请求尺寸”是提交给 Forge 的 `width × height`，“结果图层”是完成插件插入和缩放后的 GIMP 图层尺寸。局部重绘全分辨率模式另有 Forge 内部裁剪与合成步骤。

| 流程 | 输入和选区 | 请求尺寸 | 结果图层与位置 | seed |
| --- | --- | --- | --- | --- |
| 文生图，批量 2 张 | 画布 640×512；选区 `(64,48,384,320)`；`Resize to selection` | 512×512 | 两张均为 384×320，偏移 `(64,48)`，附带选区蒙版 | 12345、12346 |
| 图生图 | 来源层 512×384，偏移 `(32,24)`；选区 `(96,80,384,256)`；界面宽高 512×512 | 384×256 | 384×256，偏移 `(0,0)` | 22345 |
| 选区局部重绘 | 同一来源层；选区 `(96,80,384,256)`；`inpaint_full_res=false` | 512×512 | 384×256，偏移 `(0,0)` | 32345 |
| 图层蒙版局部重绘 | 同一来源层及其 512×384 蒙版；选区为空；`inpaint_full_res=true` | 512×512 | 640×512，偏移 `(0,0)` | 42345 |

四种流程均产生结果图层，过程返回 `Gimp.PDBStatusType.SUCCESS`。候选图层保存 `gimpfusion` Parasite，其中包含 `info` 和 `seed`。测试结果已保存为 XCF，供界面检查。

批量 2 张时，当前顶层图层顺序为 seed 12346、12345、来源层。两张候选均可见，后插入的候选位于上方并被选中。S5 据此改为按返回顺序组织图层组，并默认选择首张候选。

图生图原先强制发送 `never oom integrated.args=[true,true]`，本机 Forge 在该请求中返回 `Inference tensors do not track version counter`。删除这段强制设置后，同一测试图像和参数生成成功。修正位于 [img2img.py](../sg_plugins/img2img.py)。

## S2–S5 共用参数约定

以下规则来自 [generation_base.py](../sg_plugins/generation_base.py)、[txt2img.py](../sg_plugins/txt2img.py)、[img2img.py](../sg_plugins/img2img.py)、[inpainting.py](../sg_plugins/inpainting.py) 和 [sg_structures.py](../sg_structures.py)，并与上表实测对应。

| 项目 | 当前行为 | 后续阶段采用的约定 |
| --- | --- | --- |
| 正向提示词 | 本次提示词 + 一个空格 + 公共后缀，最后去除首尾空白 | S2 保持该顺序；S4 在最终请求处合成启用的 LoRA 标签 |
| 负向提示词 | 本次负向提示词 + 一个空格 + 公共负向后缀，最后去除首尾空白 | S2 保持该顺序 |
| seed | PDB 范围为 0–65535；请求构建将 0 转成 -1 | S2 统一为 -1 表示随机，非负整数表示指定种子 |
| 批量 | `batch_size`，范围 1–20；请求使用单次迭代 | S5 按 `all_seeds` 的顺序对应候选和 infotext |
| 尺寸取整 | `8 * round(value / 8)`，按 Python 的四舍六入五成双规则取最近的 8 倍数 | 界面显示取整后的实际请求尺寸 |
| 文生图尺寸 | 使用界面宽高；`Use selection size` 改用选区包围盒宽高 | 将请求尺寸与结果插入范围分别展示 |
| 图生图尺寸 | 使用选区包围盒宽高；选区为空时使用画布宽高 | S2 显示该模式实际采用的尺寸 |
| 局部重绘尺寸 | 使用界面宽高作为 Forge 采样尺寸 | 单独显示采样尺寸、来源尺寸和结果插入范围 |
| 来源图层 | `image.get_selected_layers()[0]`；编码整张来源层的像素 | S3 展示并刷新该层的名称、缩略图和偏移 |
| 蒙版来源 | 当前选区优先，随后使用来源图层蒙版 | S3 显示本次实际来源；选区编码为画布大小，图层蒙版保留来源层大小 |
| 蒙版像素 | 白色参与重绘，黑色保留；`invert_mask` 将请求的 `inpainting_mask_invert` 设为 1 | S3 沿用该取值方向 |
| 来源偏移 | 来源编码只包含图层像素；当前图生图和重绘结果落在 `(0,0)` | S3、S5 将来源坐标与结果插入坐标一起处理 |
| 文生图插入 | 按插入策略缩放，移动到选区左上角；局部选区附加图层蒙版 | S5 在候选组内保留同一处理规则 |
| 重绘插入 | `inpaint_full_res=true` 缩放到画布大小；false 缩放到选区包围盒大小 | S5 依据该基线统一尺寸、偏移和蒙版处理 |

提示词实测得到 `local prompt global suffix` 和 `local negative global negative`；宽高输入 513、516 均提交为 512。空选区的边界由 GIMP 返回整张画布范围。

文生图的五种插入策略：

| 策略 | 当前处理 |
| --- | --- |
| `Resize to selection` | 将候选宽高分别缩放到选区宽高 |
| `Insert as is` | 保持候选返回尺寸，定位到选区左上角 |
| `Aspect fill` | 按两轴缩放比例的较大值等比缩放，覆盖选区范围 |
| `Aspect fit` | 按两轴缩放比例的较小值等比缩放，放入选区范围 |
| `Use selection size` | 以选区宽高发起生成，保留返回尺寸并定位到选区左上角 |

## 常驻过程与 GTK 主循环

在临时 GIMP 配置中运行最小原型，通过 GIMP 菜单启动 `PERSISTENT` 过程，再从另一个插件过程调用临时 PDB 命令。实际顺序为：

1. 常驻入口创建 GTK 顶层窗口，注册 `TEMPORARY` 命令。
2. 调用 `procedure.persistent_ready()` 通知 GIMP 就绪。
3. 调用 `plug_in.persistent_enable()`，随后进入 `Gtk.main()`。
4. 临时命令接收动作和 `Gimp.Image`，执行呈现、生成动作分派及关闭。
5. 关闭动作通过 `GLib.idle_add(Gtk.main_quit)` 退出主循环；移除临时过程、销毁窗口，常驻入口返回成功。

本次 `present`、`generate`、`close` 回调均在同一个进程、同一个主线程执行，接收到相同的目标图像。GTK 100 ms 计时器在窗口存续期间持续运行；驱动中的两秒间隔里计数从 767 增至 786。关闭后 PDB 查询确认临时命令已移除。这里的 `generate` 动作验证命令分派；实际 Forge 生成见前述四种流程。

本机测试还确认了启动入口的约束：

- 带参数的 `PERSISTENT` 菜单过程由 GIMP 异步启动，GIMP 主窗口继续响应菜单。
- 零参数的 `PERSISTENT` 过程会在 GIMP 启动时自动执行。
- 从另一个插件中同步执行常驻过程的 `procedure.run(config)`，调用方会等待常驻过程结束。S6–S7 的首次启动由菜单过程自身承载窗口生命周期，已有窗口通过临时过程接收调用。

S6 的窗口、GIMP 图像读写和临时 PDB 回调统一在 GTK 主线程执行；HTTP 工作线程通过 `GLib.idle_add` 交回结果。常驻入口添加运行模式等参数，菜单入口共同使用临时过程名称定位已打开的窗口。

公开 API 依据：[Procedure.new](https://developer.gimp.org/api/3.0/libgimp/ctor.Procedure.new.html)、[persistent_ready](https://developer.gimp.org/api/3.0/libgimp/method.Procedure.persistent_ready.html)、[persistent_enable](https://developer.gimp.org/api/3.0/libgimp/method.PlugIn.persistent_enable.html)、[add_temp_procedure](https://developer.gimp.org/api/3.0/libgimp/method.PlugIn.add_temp_procedure.html)。

## 界面用途调研与 S8 文案依据

### ControlNet 辅助图层开关

调用链为 `cn_skip_annotator_layers` → `ResponseLayers` 的 `skip_annotator_layers` 选项 → 响应图像索引与 `len(info["all_seeds"])` 比较。该参数在 GIMP 响应处理阶段使用。

本机 Forge 的 `reference_only` 在 txt2img、img2img、inpaint 中均返回 2 张 512×512 图像，`all_seeds=[55555]`：第一张是候选，第二张是 ControlNet 辅助图。将三份实际响应分别交给 GIMP 的 `ResponseLayers`，开关效果一致：

| `cn_skip_annotator_layers` | 三种模式的实际图层结果 |
| --- | --- |
| true | 1 层：`Generated Layer 55555` |
| false | 2 层：`Annotator Layer`、`Generated Layer 55555` |

候选层保存 seed 和 infotext，辅助层作为输入参考图显示。关闭开关后，辅助层位于候选层上方。S5 将候选与辅助层分别整理，S8 可使用以下中文说明：

> 只导入生成候选。开启时导入生成候选；关闭时同时导入 ControlNet 返回的预处理图或参考图。适用于文生图、图生图和局部重绘。

服务端对应逻辑位于本机 Forge 的 `extensions-builtin/sd_forge_controlnet/scripts/controlnet.py`：`save_detected_map=true` 时，将预处理图或参考图追加到 `extra_result_images`。`cn_skip_annotator_layers` 的取值只改变这些返回图在 GIMP 中的插入结果。

### 其他说明与调用链问题

下表以插件和本机 Forge 源码核对用途；表中标出本次操作验证的条目。界面文字与四种语言译文在 S8 统一修改。

| 参数或文本 | 查明的用途及修订依据 |
| --- | --- |
| `seed` 的“0 or -1 for random” | 当前入口接收 0–65535，0 被转换为随机；S2 完成 -1/非负整数约定后同步说明 |
| `Batch count` | 实际对应 `batch_size`，表示本次返回的候选数；本次验证为 2 张 |
| `denoising_strength` | 调整图生图与局部重绘对来源内容的改动程度；文生图当前固定 `enable_hr=false`，该字段用于开启高分辨率修复后的二次采样 |
| `inpaint_full_res` 的 `Inpaint Whole Picture` | true 表示裁出蒙版区域及边距，按请求尺寸采样后合回来源；false 表示按请求尺寸处理整张来源；本次分别验证了两个取值 |
| `mask_blur` | Forge 沿 X、Y 轴对蒙版应用高斯模糊，过渡覆盖边缘两侧；图生图当前请求提供 `init_images`，该选项随重绘蒙版发挥作用 |
| `inpainting_fill` | 0：以周围颜色填充；1：保留原内容作为初始值；2：在蒙版区域使用随机 latent 噪声；3：将蒙版区域的初始 latent 置零。本次两次重绘使用 1 |
| `tiling` 的质量与速度说明 | 表示平铺纹理生成参数；文案说明无缝拼接用途 |
| `Aspect fill` / `Aspect fit` | 使用上表的最大比例覆盖、最小比例容纳规则；帮助文本与实际算法对应 |
| `weight` | ControlNet 控制强度，调节控制条件的影响 |
| `guidance_start` / `guidance_end` | 控制条件参与采样的起止进度，范围 0–1 |
| `processor_res` 的固定 bug 说明 | 预处理分辨率；实际效果由所选预处理器决定；本次 canny 以 512 成功执行 |
| `threshold_a` / `threshold_b` | 含义和范围由预处理器定义；本次 canny 使用 64/128，Reference 的 A 为 0.5 的 Style Fidelity |
| `lowvram` / `guidance` | 本机 Forge 的 `ControlNetUnit` 接收字段中包含 `guidance_start/end`；这两个旧字段在 `from_dict` 中被过滤 |
| ControlNet 图层配置 | `add_choice_argument` 返回字符串标识，当前配置处理将 `module/model` 当成列表索引；后续配置改造直接保存返回标识 |
| ControlNet 输入字段 | 当前插件发送 `input_image/mask`；本机 Forge 接收 `image/mask_image`；后续请求构建按本节接口约定调整 |
| ControlNet 预处理器列表 | 插件的固定列表与本机 64 项列表存在差异；后续配置使用服务返回的预处理器标识 |

Forge 源码核对位置：`modules/processing.py` 的 `StableDiffusionProcessingImg2Img.init`，以及 `extensions-builtin/sd_forge_controlnet/lib_controlnet/external_code.py` 的 `ControlNetUnit.from_dict`。Reference 和 canny 的运行结果覆盖了辅助图返回、阈值和处理分辨率的上述实测项。

## 检查与同步

修改的 Python 文件执行 `ruff check sg_plugins/img2img.py`，结果为 `All checks passed!`。本次代码改动删除图生图请求中的强制 Never OOM 设置。

开发目录与 GIMP 插件目录均位于 `main`，跟踪相同的 `origin/main`。已按仓库规范完成提交、开发目录 `push` 和插件目录 `pull --ff-only`。

同步后重启正常配置的 GIMP，确认 GimpFusion 菜单包含配置、文生图、图生图、局部重绘和 ControlNet 图层入口。通过安装副本的 `stable-gimpfusion-img2img` 再次生成成功，返回 `SUCCESS`；生成层的 seed 为 22345、尺寸为 384×256，包含对应的 infotext，并已在 GIMP 图层面板中显示。
