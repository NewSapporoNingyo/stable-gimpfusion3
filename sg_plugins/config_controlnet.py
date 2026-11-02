from __future__ import annotations

from typing import Any

import gi

from sg_constants import CONTROL_MODES, CONTROLNET_RESIZE_MODES
from sg_i18n import _
from sg_plugins import PluginBase
from sg_proc_arguments import PLUGIN_FIELDS_CONTROLNET
from sg_structures import Layer

gi.require_version("Gimp", "3.0")
gi.require_version("GimpUi", "3.0")
from gi.repository import Gimp, GimpUi, GLib


class ConfigControlnetLayerPlugin(PluginBase):
    menu_path = "<Image>/GimpFusion"
    menu_label = _("Active layer as ControlNet")
    description = _("Convert current layer to ControlNet layer or edit ControlNet Layer's options")
    sensitivity_mask = Gimp.ProcedureSensitivityMask.DRAWABLE | Gimp.ProcedureSensitivityMask.DRAWABLES

    def add_arguments(self, procedure: Gimp.Procedure) -> None:
        PLUGIN_FIELDS_CONTROLNET(
            procedure,
            cn_modules=self.settings.get("cn_modules"),
            cn_models=self.settings.get("cn_models"),
            cn_resize_modes=CONTROLNET_RESIZE_MODES,
            control_modes=CONTROL_MODES,
        )

    def main(
        self,
        procedure: Gimp.Procedure,
        run_mode: Gimp.RunMode,
        image: Gimp.Image,
        drawables: list[Gimp.Drawable],
        config: Gimp.ProcedureConfig,
        data: Any,
    ) -> Gimp.ProcedureReturn:
        if run_mode == Gimp.RunMode.INTERACTIVE:
            GimpUi.init(procedure.get_name())
            dialog = GimpUi.ProcedureDialog.new(procedure, config)

            dialog.get_scale_entry("weight", 1).set_increments(0.05, 0.5)
            dialog.get_scale_entry("guidance_start", 1).set_increments(0.25, 0.5)
            dialog.get_scale_entry("guidance_end", 1).set_increments(0.25, 0.5)
            dialog.get_scale_entry("processor_res", 1).set_increments(8, 64)
            dialog.get_scale_entry("threshold_a", 1).set_increments(8, 64)
            dialog.get_scale_entry("threshold_b", 1).set_increments(8, 64)
            dialog.fill(
                [
                    "module",
                    "model",
                    "weight",
                    "resize_mode",
                    "control_mode",
                    "guidance_start",
                    "guidance_end",
                    "processor_res",
                    "threshold_a",
                    "threshold_b",
                ],
            )

            if not dialog.run():
                return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())

        module = config.get_property("module")
        model = config.get_property("model")
        weight = config.get_property("weight")
        resize_mode = config.get_property("resize_mode")
        control_mode = config.get_property("control_mode")
        guidance_start = config.get_property("guidance_start")
        guidance_end = config.get_property("guidance_end")
        processor_res = config.get_property("processor_res")
        threshold_a = config.get_property("threshold_a")
        threshold_b = config.get_property("threshold_b")

        cn_settings = {
            "module": module,
            "model": model,
            "weight": weight,
            "resize_mode": resize_mode,
            "control_mode": control_mode,
            "guidance_start": guidance_start,
            "guidance_end": guidance_end,
            "processor_res": processor_res,
            "threshold_a": threshold_a,
            "threshold_b": threshold_b,
        }
        for active_layer in drawables:
            cnlayer = Layer(active_layer)
            cnlayer.saveData(cn_settings)
            cnlayer.rename(f"ControlNet{cnlayer.id}")

        return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())
