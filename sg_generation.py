"""Serializable generation parameters and Forge request construction."""

from __future__ import annotations

from typing import Any

from sg_constants import INPAINT_FILL_MODES, RESIZE_MODES
from sg_i18n import _

GENERATION_MODES = ("txt2img", "img2img", "inpaint")
CONTROLNET_PARAMETERS = (
    "module", "model", "weight", "resize_mode", "control_mode", "guidance_start",
    "guidance_end", "processor_res", "threshold_a", "threshold_b",
)
GENERATION_PARAMETERS = (
    "generation_mode", "sd_model_checkpoint", "prompt", "negative_prompt", "seed", "batch_size", "steps",
    "cfg_scale", "width", "height", "sampler_index", "restore_faces", "tiling", "denoising_strength",
    "resize_mode", "mask_blur", "inpainting_fill", "inpaint_full_res", "invert_mask", "insert_mode",
    "cn1_enabled", "cn2_enabled", "cn_skip_annotator_layers",
    *(f"cn{slot}_{name}" for slot in (1, 2) for name in CONTROLNET_PARAMETERS),
)


def integer_seed(value: float | int) -> int:
    if not -1 <= value <= 4294967295 or int(value) != value:
        raise ValueError(_("Seed must be an integer from -1 to 4294967295"))
    return int(value)


def generation_size(values: dict[str, Any], selection_size: tuple[int, int]) -> tuple[int, int]:
    if values["generation_mode"] == "img2img" or (
        values["generation_mode"] == "txt2img" and values["insert_mode"] == "Use selection size"
    ):
        width, height = selection_size
    else:
        width, height = values["width"], values["height"]
    return 8 * round(width / 8), 8 * round(height / 8)


def insertion_size(
    values: dict[str, Any], selection_size: tuple[int, int], image_size: tuple[int, int],
) -> tuple[int, int]:
    mode = values["generation_mode"]
    if mode == "inpaint":
        return image_size if values["inpaint_full_res"] else selection_size
    width, height = generation_size(values, selection_size)
    if mode == "img2img" or values["insert_mode"] in ("Insert as is", "Use selection size"):
        return width, height
    if values["insert_mode"] == "Resize to selection":
        return selection_size
    ratios = selection_size[0] / width, selection_size[1] / height
    scale = max(ratios) if values["insert_mode"] == "Aspect fill" else min(ratios)
    return int(width * scale), int(height * scale)


def build_request(
    values: dict[str, Any], prompt_suffix: str, negative_suffix: str, selection_size: tuple[int, int],
) -> dict[str, Any]:
    width, height = generation_size(values, selection_size)
    data = {name: values[name] for name in (
        "batch_size", "steps", "cfg_scale", "sampler_index", "restore_faces", "tiling",
    )}
    data.update({
        "prompt": f"{values['prompt']} {prompt_suffix}".strip(),
        "negative_prompt": f"{values['negative_prompt']} {negative_suffix}".strip(),
        "seed": integer_seed(values["seed"]), "width": width, "height": height,
    })
    if values["generation_mode"] == "txt2img":
        data["enable_hr"] = False
    else:
        data.update({
            "denoising_strength": values["denoising_strength"],
            "resize_mode": RESIZE_MODES.index(values["resize_mode"]), "mask_blur": values["mask_blur"],
        })
        if values["generation_mode"] == "inpaint":
            data.update({
                "inpainting_fill": INPAINT_FILL_MODES.index(values["inpainting_fill"]),
                "inpaint_full_res": values["inpaint_full_res"], "inpaint_full_res_padding": 10,
                "inpainting_mask_invert": int(values["invert_mask"]),
            })
    return data
