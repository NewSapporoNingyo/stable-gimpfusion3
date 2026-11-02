#!/usr/bin/env python3
from __future__ import annotations

import logging
import os
import sys

import gi

from sg_i18n import DOMAIN
from sg_plugins import PluginBase
from sg_plugins.config import ConfigModelPlugin, ConfigPlugin
from sg_plugins.config_controlnet import ConfigControlnetLayerPlugin
from sg_plugins.img2img import Image2imagePlugin
from sg_plugins.inpainting import InpaintingPlugin
from sg_plugins.layerinfo import LayerInfoPlugin
from sg_plugins.txt2img import Txt2imagePlugin

gi.require_version("Gimp", "3.0")
gi.require_version("GimpUi", "3.0")
from gi.repository import Gimp

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sg_constants import (
    AUTHOR,
    STABLE_GIMPFUSION_DEFAULT_SETTINGS,
)
from sg_structures import ApiClient, Layer, MyShelf
from sg_utils import fetch_stablediffusion_options, set_logging_dest

settings = MyShelf(STABLE_GIMPFUSION_DEFAULT_SETTINGS)
api = ApiClient(settings.get("api_base"))

logging.basicConfig(level=logging.DEBUG if settings.get("debug_logging") else logging.INFO)
set_logging_dest(settings.get("file_logging") or False)

MODULES: dict[str, PluginBase] = {
    "stable-gimpfusion-config": ConfigPlugin(api=api, settings=settings),
    "stable-gimpfusion-config-model": ConfigModelPlugin(api=api, settings=settings),
    "stable-gimpfusion-txt2img": Txt2imagePlugin(api=api, settings=settings),
    "stable-gimpfusion-img2img": Image2imagePlugin(api=api, settings=settings),
    "stable-gimpfusion-inpainting": InpaintingPlugin(api=api, settings=settings),
    "stable-gimpfusion-config-controlnet-layer": ConfigControlnetLayerPlugin(api=api, settings=settings),
    "stable-gimpfusion-layer-info": LayerInfoPlugin(api=api, settings=settings),
}


class GimpfusionPlugin(Gimp.PlugIn):
    def __init__(self):
        super().__init__()

        try:
            options = fetch_stablediffusion_options(api=api)
            settings.save(options)
        except Exception:
            logging.exception("ERROR: DynamicDropdownData.fetch")
            settings.save({"is_server_running": False})

        Layer.set_global_settings(settings)

    def do_set_i18n(self, name: str) -> str:
        return DOMAIN

    def do_query_procedures(self):
        return list(MODULES.keys())

    def do_create_procedure(self, name: str) -> Gimp.Procedure:
        module = MODULES[name]

        procedure = Gimp.ImageProcedure.new(
            self,
            name,
            Gimp.PDBProcType.PLUGIN,
            module.main,
            None,
        )

        procedure.set_image_types("*")
        procedure.set_sensitivity_mask(module.sensitivity_mask)

        procedure.set_menu_label(module.menu_label)
        # procedure.set_icon_name(GimpUi.ICON_GEGL)
        procedure.add_menu_path(module.menu_path)

        procedure.set_documentation(module.description, module.description, name)
        procedure.set_attribution(AUTHOR, AUTHOR, "2025")

        module.add_arguments(procedure)

        return procedure


Gimp.main(GimpfusionPlugin.__gtype__, sys.argv)
