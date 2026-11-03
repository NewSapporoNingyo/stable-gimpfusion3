"""Serializable generation parameters and Forge request construction."""

from __future__ import annotations

from typing import Any

from sg_constants import INPAINT_FILL_MODES, RESIZE_MODES
from sg_i18n import _
from sg_loras import LoraCatalog, compose_prompt

GENERATION_MODES = ("txt2img", "img2img", "inpaint")
CONTROLNET_PARAMETERS = (
    "module", "model", "weight", "resize_mode", "control_mode", "guidance_start",
    "guidance_end", "processor_res", "threshold_a", "threshold_b",
)
GENERATION_PARAMETERS = (
    "generation_mode", "sd_model_checkpoint", "prompt", "negative_prompt", "seed", "batch_size", "steps",
    "cfg_scale", "width", "height", "sampler_index", "restore_faces", "tiling", "denoising_strength",
    "resize_mode", "mask_blur", "inpainting_fill", "inpaint_full_res", "inpaint_full_res_padding",
    "invert_mask", "insert_mode",
    "cn1_enabled", "cn2_enabled", "cn_skip_annotator_layers",
    *(f"cn{slot}_{name}" for slot in (1, 2) for name in CONTROLNET_PARAMETERS),
)


def integer_seed(value: float | int) -> int:
    if not -1 <= value <= 4294967295 or int(value) != value:
        raise ValueError(_("Seed must be an integer from -1 to 4294967295"))
    return int(value)


def validate_dimensions(width: int, height: int) -> None:
    if width <= 0 or height <= 0 or width % 8 or height % 8:
        raise ValueError(_("Width and height must be positive multiples of 8"))


def generation_size(values: dict[str, Any], selection_size: tuple[int, int]) -> tuple[int, int]:
    if values["generation_mode"] == "txt2img" and values["insert_mode"] == "Use selection size":
        width, height = selection_size
        return 8 * round(width / 8), 8 * round(height / 8)
    return values["width"], values["height"]


def aspect_resize(area: tuple[int, int], image: tuple[int, int], *, fill: bool) -> tuple[int, int]:
    ratios = area[0] / image[0], area[1] / image[1]
    scale = max(ratios) if fill else min(ratios)
    return int(image[0] * scale), int(image[1] * scale)


def insertion_size(
    values: dict[str, Any], selection_size: tuple[int, int], source_size: tuple[int, int],
) -> tuple[int, int]:
    mode = values["generation_mode"]
    if mode == "inpaint" and values["inpaint_full_res"]:
        return source_size
    width, height = generation_size(values, selection_size)
    if mode in ("img2img", "inpaint") or values["insert_mode"] in ("Insert as is", "Use selection size"):
        return width, height
    if values["insert_mode"] == "Resize to selection":
        return selection_size
    return aspect_resize(selection_size, (width, height), fill=values["insert_mode"] == "Aspect fill")


def build_request(
    values: dict[str, Any], prompt_suffix: str, negative_suffix: str, selection_size: tuple[int, int],
    lora_catalog: LoraCatalog,
) -> dict[str, Any]:
    width, height = generation_size(values, selection_size)
    validate_dimensions(width, height)
    data = {name: values[name] for name in (
        "batch_size", "steps", "cfg_scale", "sampler_index", "restore_faces", "tiling",
    )}
    data.update({
        "prompt": compose_prompt(values["prompt"], prompt_suffix, values["loras"], lora_catalog)[0],
        "negative_prompt": f"{values['negative_prompt']} {negative_suffix}".strip(),
        "seed": values["seed"], "width": width, "height": height,
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
                "inpaint_full_res": values["inpaint_full_res"],
                "inpaint_full_res_padding": values["inpaint_full_res_padding"],
                "inpainting_mask_invert": int(values["invert_mask"]),
            })
    return data
