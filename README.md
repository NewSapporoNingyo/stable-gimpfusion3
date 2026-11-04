# Stable-Gimpfusion-3

English | [简体中文](README.zh-CN.md)

Generate images in GIMP 3.2 through the Stable Diffusion WebUI Forge HTTP API, using text to image, image to image, inpainting and ControlNet.
A persistent window lets you edit in GIMP while generating, with results inserted as layers.

This fork builds on [shsmad's GIMP 3 version](https://github.com/shsmad/stable-gimpfusion3) of
[ArtBIT's GIMP 2.10 plugin](https://github.com/ArtBIT/stable-gimpfusion). The local acceptance environment is Windows, GIMP 3.2.6, GIMP Python 3.14.7 and Forge.

## Installation and connection

1. Place the complete repository in `%APPDATA%\GIMP\3.2\plug-ins\stable-gimpfusion3`, including the entry script, all `sg_*.py` files, `sg_plugins` and `locale`.
2. Confirm that `import requests` succeeds with GIMP's Python, located at `bin\python.exe` inside the GIMP installation.
3. Start Forge with `--api`. The local launcher is `C:\data\webui_forge_dev\run-forge.bat`, using `--api --cuda-malloc`.
4. Restart GIMP. Set the backend address in `GimpFusion → Config → Global`; the default is `http://127.0.0.1:7860`.
5. Open or create an image and choose `GimpFusion → Open generation panel`. The Text to image, Image to image and Inpainting menu entries open the same panel in their respective modes.

The plugin follows GIMP's interface language and provides English, Italian, Russian and Simplified Chinese.
Choose the language in GIMP's Edit → Preferences → Interface settings, then restart GIMP.

## Persistent panel and generation

Choose the target image and generation mode at the top of the panel. Enter positive and negative prompts, choose a model, sampler and parameters, then click Generate.
Both prompt editors show eight lines. Parameters, LoRA and settings operations expand within the panel.
Global prompt suffixes are appended as “local prompt + space + suffix”.

Seed `-1` selects a random seed; `0` through `4294967295` select a fixed seed. Candidates sets the number of images generated in one batch.
Width and height use positive multiples of 8. The panel displays request dimensions and the insertion area.
Higher denoising strength allows greater changes to the source in img2img and inpaint.

| Mode | Input and result |
| --- | --- |
| txt2img | Generate from prompts. The insertion mode sets result dimensions; results start at the selection's top-left corner. An empty selection uses the canvas bounds |
| img2img | Use the complete pixels of the first selected layer in the target image. Generate at the panel dimensions and insert at the source offset |
| inpaint | Use the source layer and a mask, with the current selection taking precedence over the source layer mask. White is repainted; Invert Mask selects black |

Input source shows the target, layer, preview, dimensions, offset and actual mask source. It refreshes when the target or selected layer changes and when the panel regains focus.
Generation captures the latest input snapshot. Whole picture samples the entire source; Only masked samples the mask and padding, then composites into the source dimensions.
The default mask fill mode is `original`.

During generation you can paint, edit parameters and switch targets. The current task uses its initial input and target; the next task uses the latest state.
The panel runs one task at a time. Results become separate layers: choose candidates through layer visibility, undo the insertion in one step and continue editing.
The checkbox at the bottom enables a Windows system notification after successful insertion.

## Settings files and XCF data

Expand Generation settings to use these operations:

- Save file as opens the Windows file dialog and writes prompts, model and generation parameters to a UTF-8 INI document with a `.txt` extension.
- Load file reads the selected file, keeps the panel's current mode and restores common fields and applicable mode fields.
- Save file writes changes to the current file and asks for a path on the first save.
- Save to image manually attaches the current settings to the target image; save the image as `.xcf` afterwards.
- Load from image manually restores the settings attached to the current target image.

The same settings file works across all three modes. For example, denoising strength applies to img2img and inpaint; mode fields remain in the saved file.
Closing the panel saves the latest parameters, current file path, window dimensions and notification setting for the next opening.
Save to image updates the XCF attachment, which participates in GIMP undo and survives saving and reopening the XCF.

## LoRA and ControlNet

Search LoRA names or aliases. Click a model to add `<lora:identifier:weight>` to the positive prompt; click again to remove its tag.
Edit weights directly in the prompt, including negative values and `0`. New tags use Forge's default weight, name preference and separator settings.
Refresh LoRAs rescans Forge's directory; LoRA details shows paths and metadata. Tags are saved with the prompt in settings files and image data.

ControlNet supports two inputs. Enable a slot, choose an input layer in the current target and expand its parameters to set the preprocessor, model, weight and sampling start/end progress.
Read layer settings loads parameters saved through Active layer as ControlNet. Select input layers again after switching targets.
Threshold meanings depend on the selected preprocessor. Reference preprocessors can use model `None`.

Import candidates only imports generated candidates when enabled. Disable it to also import preprocessing or reference images returned by ControlNet. This applies to all three modes.

## Windows snapping and keyboard shortcut

Drag the panel edges to resize it; the minimum size is 360×480. Drag GIMP's title bar to one side of the screen and select the panel in Windows Snap Assist.
Drag the divider to adjust their proportions.

1. Open Edit → Keyboard Shortcuts in GIMP.
2. Search for `stable-gimpfusion-generate-current` or Generate with current parameters.
3. Select its shortcut column, press `Ctrl+Alt+G` and save.
4. Set panel parameters, return to the canvas, paint and press the shortcut to generate.

The shortcut receives GIMP's current image and uses the panel's current mode and parameters.
With the panel closed, it restores the last parameters and generates; an existing panel receives the command directly.

## Translation and development

Update translations with GNU gettext:

```bash
bash update-translations.sh
```

The script extracts production messages, merges en, it, ru and zhcn, checks completeness and format placeholders, and compiles `.mo` files.
Maintain Chinese translations in `locale/zhcn/LC_MESSAGES`; the script generates the `locale/zh_CN` binary for GIMP's native menus.
Mark interface text with `sg_i18n._()`. Keep API fields, model names, sampler names and technical option identifiers in their original form.

Development, synchronization and checks are described in the Chinese [repository guide](AGENTS.md), [development plan](doc/devplan.md) and [TODO](TODO.md).
Feature records cover the [persistent panel](doc/s5-panel.md), [generation settings](doc/s6-generation-settings.md) and [keyboard shortcut](doc/s7-shortcuts.md).
