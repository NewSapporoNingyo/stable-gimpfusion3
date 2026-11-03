from __future__ import annotations

import logging
import os
import tempfile

from typing import TYPE_CHECKING, Any

import gi

if TYPE_CHECKING:
    from sg_structures import ApiClient

gi.require_version("Gimp", "3.0")
from gi.repository import Gimp


def make_choice_from_list(data: list[str]) -> Gimp.Choice:
    choice = Gimp.Choice.new()
    # nick, id, label, help
    for key, value in enumerate(data):
        choice.add(value, key, value, value)

    return choice


def fetch_stablediffusion_options(api: ApiClient) -> dict[str, Any]:
    """Get the StableDiffusion data needed for dynamic gimpfu.PF_OPTION lists"""

    options = api.get("/sdapi/v1/options")
    sd_model_checkpoint = options["sd_model_checkpoint"]
    models = [x["title"].removesuffix(f" [{x['hash']}]") for x in api.get("/sdapi/v1/sd-models")]
    cn_models = api.get("/controlnet/model_list")["model_list"]
    cn_modules = api.get("/controlnet/module_list")["module_list"]
    samplers = [sampler["name"] for sampler in api.get("/sdapi/v1/samplers")]
    sd_modules = [x["filename"] for x in api.get("/sdapi/v1/sd-modules")]
    gradio_config = api.get("/config")
    lora_preferred_name = next(
        component["props"]["value"] for component in gradio_config["components"]
        if component["props"].get("elem_id") == "setting_lora_preferred_name"
    )

    return {
        "models": models,
        "sd_modules": sd_modules,
        "cn_models": cn_models,
        "cn_modules": cn_modules,
        "samplers": samplers,
        "sd_model_checkpoint": sd_model_checkpoint,
        "lora_preferred_name": lora_preferred_name,
        "is_server_running": True,
        "has_sd_modules_support": True,
    }


def set_logging_dest(use_file_logging: bool) -> None:
    logging_file = os.path.join(tempfile.gettempdir(), "gimpfusion.log")
    new_handler = logging.FileHandler(logging_file) if use_file_logging else logging.StreamHandler()
    new_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    root_logger = logging.getLogger()
    for old_handler in root_logger.handlers[:]:
        root_logger.removeHandler(old_handler)
    root_logger.addHandler(new_handler)
