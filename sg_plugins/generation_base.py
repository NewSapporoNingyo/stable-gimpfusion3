"""Shared generation dialog, named presets and GIMP/Forge integration."""

from __future__ import annotations

import json
import math
import threading

from typing import Any

import gi
import requests

from sg_constants import CONTROL_MODES, CONTROLNET_RESIZE_MODES, INPAINT_FILL_MODES, RESIZE_MODES
from sg_generation import (
    CONTROLNET_PARAMETERS,
    GENERATION_MODES,
    GENERATION_PARAMETERS,
    build_request,
    generation_size,
    insertion_size,
    integer_seed,
)
from sg_gtk_utils import add_textarea_to_container
from sg_i18n import _
from sg_plugins import PluginBase
from sg_proc_arguments import (
    PLUGIN_FIELDS_COMMON,
    PLUGIN_FIELDS_CONTROLNET,
    PLUGIN_FIELDS_CONTROLNET_OPTIONS,
    PLUGIN_FIELDS_INPAINTING,
    PLUGIN_FIELDS_RESIZE_MODE,
)
from sg_structures import (
    Layer,
    LayerData,
    ResponseLayers,
    getActiveLayerAsBase64,
    getActiveMaskAsBase64,
    getLayerAsBase64,
)
from sg_utils import get_progress_at_background, make_choice_from_list

gi.require_version("Gimp", "3.0")
gi.require_version("GimpUi", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gimp, GimpUi, GLib, GObject, Gtk


class GenerationPluginBase(PluginBase):
    initial_mode: str

    def add_arguments(self, procedure: Gimp.Procedure) -> None:
        flags = GObject.ParamFlags.READWRITE
        procedure.add_choice_argument(
            "generation_mode", _("Generation mode"), _("Generation mode"),
            make_choice_from_list(list(GENERATION_MODES)), self.initial_mode, flags,
        )
        models = self.settings.get("models")
        procedure.add_choice_argument(
            "sd_model_checkpoint", _("Model"), _("Model to use for inference"),
            make_choice_from_list(models), self.settings.get("sd_model_checkpoint"), flags,
        )
        PLUGIN_FIELDS_COMMON(procedure, self.settings.get("samplers"), self.settings.get("sampler_name"))
        PLUGIN_FIELDS_RESIZE_MODE(procedure, RESIZE_MODES)
        PLUGIN_FIELDS_INPAINTING(procedure, INPAINT_FILL_MODES)
        PLUGIN_FIELDS_CONTROLNET_OPTIONS(procedure)
        for slot in (1, 2):
            PLUGIN_FIELDS_CONTROLNET(
                procedure, self.settings.get("cn_modules"), self.settings.get("cn_models"),
                CONTROLNET_RESIZE_MODES, CONTROL_MODES, prefix=f"cn{slot}_",
            )
        procedure.add_string_argument("loras", "LoRA", "LoRA", "[]", flags)

    def collect_values(self, config: Gimp.ProcedureConfig) -> dict[str, Any]:
        values = {name: config.get_property(name) for name in GENERATION_PARAMETERS}
        values["seed"] = integer_seed(values["seed"])
        values["loras"] = json.loads(config.get_property("loras"))
        return values

    def validate_preset(self, procedure: Gimp.Procedure, preset: dict[str, Any]) -> None:
        config = procedure.create_config()
        for name in GENERATION_PARAMETERS:
            value = preset[name]
            spec = procedure.find_argument(name.replace("_", "-"))
            expected_type = type(config.get_property(name))
            valid_type = type(value) in (int, float) if expected_type is float else type(value) is expected_type
            if not valid_type:
                raise ValueError(_("Invalid preset field: {field}").format(field=name))
            if expected_type in (int, float) and (
                not math.isfinite(value) or not spec.minimum <= value <= spec.maximum
            ):
                raise ValueError(_("Invalid preset field: {field}").format(field=name))
            if (
                expected_type is str and name not in ("prompt", "negative_prompt")
                and not Gimp.param_spec_choice_get_choice(spec).is_valid(value)
            ):
                raise ValueError(_("Unavailable preset option: {field} = {value}").format(field=name, value=value))
        integer_seed(preset["seed"])
        if not isinstance(preset["loras"], list):
            raise ValueError(_("Invalid preset field: {field}").format(field="loras"))
        for lora in preset["loras"]:
            if (
                not isinstance(lora["name"], str) or not isinstance(lora["alias"], str)
                or type(lora["enabled"]) is not bool or type(lora["weight"]) not in (int, float)
                or not math.isfinite(lora["weight"])
            ):
                raise ValueError(_("Invalid preset field: {field}").format(field="loras"))

    def main(
        self, procedure: Gimp.Procedure, run_mode: Gimp.RunMode, image: Gimp.Image,
        drawables: list[Gimp.Drawable], config: Gimp.ProcedureConfig, data: Any,
    ) -> Gimp.ProcedureReturn:
        try:
            if run_mode == Gimp.RunMode.INTERACTIVE:
                config.set_property("generation_mode", self.initial_mode)
                GimpUi.init(procedure.get_name())
                editor = GenerationDialog(self, procedure, config, image)
                accepted = editor.dialog.run()
                editor.dialog.destroy()
                if not accepted:
                    return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error())
            values = self.collect_values(config)
            self.generate(image, config, values)
            return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())
        except (requests.RequestException, ValueError, OSError) as error:
            Gimp.message(str(error))
            return procedure.new_return_values(Gimp.PDBStatusType.CALLING_ERROR, GLib.Error(message=str(error)))
        finally:
            Gimp.progress_end()

    def generate(self, image: Gimp.Image, config: Gimp.ProcedureConfig, values: dict[str, Any]) -> None:
        _success, _non_empty, x1, y1, x2, y2 = Gimp.Selection.bounds(image)
        size = x2 - x1, y2 - y1
        data = build_request(values, self.settings.get("prompt"), self.settings.get("negative_prompt"), size)
        mode = values["generation_mode"]
        if mode != "txt2img":
            data["init_images"] = [getActiveLayerAsBase64(image)]
        if mode == "inpaint":
            mask = getActiveMaskAsBase64(image)
            if not mask:
                raise ValueError(_("Inpainting must use either a selection or layer mask"))
            data["mask"] = mask
        units = []
        for slot in (1, 2):
            if values[f"cn{slot}_enabled"]:
                layer = config.get_property(f"cn{slot}_layer")
                if layer is None or layer.get_image() != image:
                    raise ValueError(_("Select a ControlNet input layer from the current image"))
                unit = {name: values[f"cn{slot}_{name}"] for name in CONTROLNET_PARAMETERS}
                unit["resize_mode"] = CONTROLNET_RESIZE_MODES.index(unit["resize_mode"])
                unit["control_mode"] = CONTROL_MODES.index(unit["control_mode"])
                unit["image"] = getLayerAsBase64(layer)
                if layer.get_mask() is not None:
                    unit["mask_image"] = Layer(layer).maskToBase64()
                units.append(unit)
        if units:
            data["alwayson_scripts"] = {"controlnet": {"args": units}}
        endpoint = "/sdapi/v1/txt2img" if mode == "txt2img" else "/sdapi/v1/img2img"
        Gimp.progress_init(_("Generating image"))
        self.api.post("/sdapi/v1/options", {"sd_model_checkpoint": values["sd_model_checkpoint"]})
        thread = threading.Thread(target=get_progress_at_background, args=(self.api,), daemon=True)
        thread.start()
        try:
            response = self.api.post(endpoint, data)
        finally:
            thread.join()
        Gimp.progress_set_text(_("Inserting layers from response"))
        layers = ResponseLayers(image, response, {"skip_annotator_layers": values["cn_skip_annotator_layers"]})
        if mode == "txt2img":
            layers.resize(*size, strategy=values["insert_mode"]).translate((x1, y1)).addSelectionAsMask()
        elif mode == "inpaint":
            width, height = (image.get_width(), image.get_height()) if values["inpaint_full_res"] else size
            layers.resize(width, height)


class GenerationDialog:
    def __init__(
        self, plugin: GenerationPluginBase, procedure: Gimp.Procedure, config: Gimp.ProcedureConfig, image: Gimp.Image,
    ) -> None:
        self.plugin = plugin
        self.procedure = procedure
        self.config = config
        self.image = image
        self.active_preset = ""
        self.dialog = GimpUi.ProcedureDialog.new(procedure, config, _("GimpFusion generation"))
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.dialog.get_content_area().add(root)
        row = Gtk.Box(spacing=6)
        root.pack_start(row, False, False, 0)
        self.preset_list = Gtk.ComboBoxText()
        row.pack_start(self.preset_list, True, True, 0)
        self.save_button = Gtk.Button(label=_("Save preset"))
        for button, callback in (
            (Gtk.Button(label=_("Load preset")), self.load_selected),
            (self.save_button, self.save_current),
            (Gtk.Button(label=_("Save preset as")), self.save_as),
            (Gtk.Button(label=_("Delete preset")), self.delete_selected),
        ):
            row.pack_start(button, False, False, 0)
            button.connect("clicked", callback)
        self.current_label = Gtk.Label(xalign=0)
        root.pack_start(self.current_label, False, False, 0)
        self.error_label = Gtk.Label(xalign=0, wrap=True)
        root.pack_start(self.error_label, False, False, 0)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(450)
        root.pack_start(scroll, True, True, 0)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        scroll.add(body)
        self.dialog.get_widget("generation_mode", Gtk.ComboBox.__gtype__)
        self.dialog.get_widget("sd_model_checkpoint", Gtk.ComboBox.__gtype__)
        body.add(self.dialog.fill_box("mode_model", ["generation_mode", "sd_model_checkpoint"]))
        add_textarea_to_container(procedure, config, "prompt", body)
        add_textarea_to_container(procedure, config, "negative-prompt", body)
        seed_widget = self.dialog.get_widget("seed", GimpUi.LabelSpin.__gtype__)
        seed_widget.get_spin_button().set_digits(0)
        seed_widget.get_spin_button().set_increments(1, 100)
        self.dialog.get_scale_entry("width", 1).set_increments(8, 64)
        self.dialog.get_scale_entry("height", 1).set_increments(8, 64)
        self.dialog.get_scale_entry("cfg_scale", 1).set_increments(0.5, 1)
        grid = Gtk.Grid(column_spacing=8, row_spacing=8, column_homogeneous=True)
        body.add(grid)
        self.width_box = self.dialog.fill_box("width_box", ["width"])
        self.height_box = self.dialog.fill_box("height_box", ["height"])
        grid.attach(self.width_box, 0, 0, 2, 1)
        grid.attach(self.height_box, 2, 0, 2, 1)
        for column, name in enumerate(("seed", "steps", "cfg_scale", "batch_size")):
            grid.attach(self.dialog.fill_box(name + "_box", [name]), column, 1, 1, 1)
        body.add(self.dialog.fill_box("common_options", ["sampler_index", "restore_faces", "tiling"]))
        self.mode_boxes = {
            "txt2img": self.dialog.fill_box("txt_options", ["insert_mode"]),
            "image": self.dialog.fill_box("image_options", ["denoising_strength", "resize_mode", "mask_blur"]),
            "inpaint": self.dialog.fill_box("inpaint_options", ["invert_mask", "inpaint_full_res", "inpainting_fill"]),
        }
        for box in self.mode_boxes.values():
            body.add(box)
        self.size_label = Gtk.Label(xalign=0, wrap=True)
        body.add(self.size_label)
        for slot in (1, 2):
            body.add(self.dialog.fill_box(f"cn{slot}_input", [f"cn{slot}_enabled", f"cn{slot}_layer"]))
            expander = Gtk.Expander(label=_("ControlNet {slot} parameters").format(slot=slot))
            cn_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            expander.add(cn_box)
            cn_box.add(self.dialog.fill_box(f"cn{slot}_parameters", [f"cn{slot}_{n}" for n in CONTROLNET_PARAMETERS]))
            read_button = Gtk.Button(label=_("Read layer settings"))
            read_button.connect("clicked", self.read_layer, slot)
            cn_box.add(read_button)
            body.add(expander)
        body.add(self.dialog.fill_box("output_options", ["cn_skip_annotator_layers"]))
        root.show_all()
        self.dialog.resize(860, 760)
        config.connect("notify", self.refresh_mode)
        last = plugin.settings.get("last_preset")
        self.refresh_presets(last)
        if last is not None:
            self.load_selected(same_mode_only=True)
        self.refresh_mode()

    def refresh_presets(self, selected: str | None) -> None:
        self.preset_list.remove_all()
        for name in self.plugin.settings.get("presets"):
            self.preset_list.append(name, name)
        self.preset_list.set_active_id(selected)
        self.save_button.set_sensitive(bool(self.active_preset))
        self.current_label.set_text(
            _("Current preset: {name}").format(name=self.active_preset)
            if self.active_preset else _("Unsaved parameters"),
        )

    def refresh_mode(self, *_args: Any) -> None:
        mode = self.config.get_property("generation_mode")
        self.mode_boxes["txt2img"].set_visible(mode == "txt2img")
        self.mode_boxes["image"].set_visible(mode != "txt2img")
        self.mode_boxes["inpaint"].set_visible(mode == "inpaint")
        use_dimensions = mode != "img2img" and not (
            mode == "txt2img" and self.config.get_property("insert_mode") == "Use selection size"
        )
        self.width_box.set_sensitive(use_dimensions)
        self.height_box.set_sensitive(use_dimensions)
        _success, _non_empty, x1, y1, x2, y2 = Gimp.Selection.bounds(self.image)
        values = {name: self.config.get_property(name) for name in (
            "generation_mode", "insert_mode", "width", "height", "inpaint_full_res",
        )}
        width, height = generation_size(values, (x2 - x1, y2 - y1))
        area_width, area_height = insertion_size(
            values, (x2 - x1, y2 - y1), (self.image.get_width(), self.image.get_height()),
        )
        self.size_label.set_text(_("Request: {width} x {height}; insertion area: {area_width} x {area_height}").format(
            width=width, height=height, area_width=area_width, area_height=area_height,
        ))
        if mode == "inpaint":
            layer = self.image.get_selected_layers()[0]
            self.size_label.set_text(self.size_label.get_text() + "\n" + _("Source: {width} x {height}").format(
                width=layer.get_width(), height=layer.get_height(),
            ))

    def load_selected(self, _button: Gtk.Button | None = None, *, same_mode_only: bool = False) -> None:
        name = self.preset_list.get_active_id()
        if name is None:
            return
        try:
            preset = self.plugin.settings.get("presets")[name]
            self.plugin.validate_preset(self.procedure, preset)
            if same_mode_only and preset["generation_mode"] != self.plugin.initial_mode:
                return
            self.plugin.settings.set("last_preset", name)
            self.config.freeze_notify()
            for field in GENERATION_PARAMETERS:
                self.config.set_property(field, preset[field])
            self.config.set_property("loras", json.dumps(preset["loras"]))
            self.config.thaw_notify()
            self.active_preset = name
            self.error_label.set_text("")
            self.refresh_presets(name)
        except (KeyError, TypeError, ValueError, OSError) as error:
            self.error_label.set_text(str(error))

    def save_current(self, *_args: Any) -> None:
        try:
            self.plugin.settings.save_preset(self.active_preset, self.plugin.collect_values(self.config))
            self.error_label.set_text("")
            self.refresh_presets(self.active_preset)
        except (ValueError, OSError) as error:
            self.error_label.set_text(str(error))

    def save_as(self, *_args: Any) -> None:
        dialog = Gtk.Dialog(title=_("Save preset as"), transient_for=self.dialog, modal=True)
        dialog.add_buttons(_("Cancel"), Gtk.ResponseType.CANCEL, _("Save preset"), Gtk.ResponseType.OK)
        entry = Gtk.Entry()
        entry.set_activates_default(True)
        dialog.set_default_response(Gtk.ResponseType.OK)
        error_label = Gtk.Label(wrap=True)
        dialog.get_content_area().add(entry)
        dialog.get_content_area().add(error_label)
        dialog.show_all()
        while dialog.run() == Gtk.ResponseType.OK:
            name = entry.get_text().strip()
            if not name:
                error_label.set_text(_("Enter a preset name"))
                continue
            if name in self.plugin.settings.get("presets"):
                error_label.set_text(_("Preset name already exists"))
                continue
            try:
                self.plugin.settings.save_preset(name, self.plugin.collect_values(self.config))
            except (ValueError, OSError) as error:
                error_label.set_text(str(error))
                continue
            self.active_preset = name
            self.refresh_presets(name)
            self.error_label.set_text("")
            break
        dialog.destroy()

    def delete_selected(self, *_args: Any) -> None:
        name = self.preset_list.get_active_id()
        if name is None:
            return
        try:
            self.plugin.settings.delete_preset(name)
            if self.active_preset == name:
                self.active_preset = ""
            self.refresh_presets(self.active_preset)
            self.error_label.set_text("")
        except OSError as error:
            self.error_label.set_text(str(error))

    def read_layer(self, _button: Gtk.Button, slot: int) -> None:
        layer = self.config.get_property(f"cn{slot}_layer")
        if layer is None or layer.get_image() != self.image:
            self.error_label.set_text(_("Select a ControlNet input layer from the current image"))
            return
        try:
            data = LayerData(layer).data
            values = self.plugin.collect_values(self.config)
            for field in CONTROLNET_PARAMETERS:
                value = data[field]
                if field == "control_mode" and isinstance(value, int):
                    value = CONTROL_MODES[value]
                values[f"cn{slot}_{field}"] = value
            self.plugin.validate_preset(self.procedure, values)
            for field in CONTROLNET_PARAMETERS:
                self.config.set_property(f"cn{slot}_{field}", values[f"cn{slot}_{field}"])
            self.error_label.set_text("")
        except (KeyError, TypeError, ValueError) as error:
            self.error_label.set_text(str(error))
