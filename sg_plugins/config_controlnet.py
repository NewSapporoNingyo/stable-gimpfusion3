from __future__ import annotations

from typing import Any

import gi

from sg_constants import CONTROL_MODES, CONTROLNET_RESIZE_MODES
from sg_generation import CONTROLNET_PARAMETERS
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
            dialog.fill(list(CONTROLNET_PARAMETERS))

            if not dialog.run():
                return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())

        cn_settings = {name: config.get_property(name) for name in CONTROLNET_PARAMETERS}
        for active_layer in drawables:
            cnlayer = Layer(active_layer)
            cnlayer.saveData(cn_settings)
            cnlayer.rename(f"ControlNet{cnlayer.id}")

        return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())
