"""Shared generation editor, portable settings and GIMP/Forge integration."""

from __future__ import annotations

import configparser
import json
import math

from concurrent.futures import ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Any, cast

import gi
import requests

from sg_constants import CONTROL_MODES, CONTROLNET_RESIZE_MODES, INPAINT_FILL_MODES, RESIZE_MODES
from sg_generation import (
    COMMON_PARAMETERS,
    CONTROLNET_PARAMETERS,
    GENERATION_MODES,
    GENERATION_PARAMETERS,
    GENERATION_PARASITE,
    MODE_PARAMETERS,
    MODE_SPECIFIC_PARAMETERS,
    build_request,
    generation_size,
    insertion_size,
    integer_seed,
    parse_generation,
    serialize_generation,
    validate_dimensions,
)
from sg_gtk_utils import add_textarea_to_container
from sg_i18n import _
from sg_loras import LoraCatalog
from sg_plugins import PluginBase
from sg_plugins.lora_selector import LoraSelector
from sg_proc_arguments import (
    PLUGIN_FIELDS_COMMON,
    PLUGIN_FIELDS_CONTROLNET,
    PLUGIN_FIELDS_CONTROLNET_OPTIONS,
    PLUGIN_FIELDS_INPAINTING,
    PLUGIN_FIELDS_RESIZE_MODE,
)
from sg_sources import GenerationSource, PixelSnapshot
from sg_structures import ApiClient, LayerData, ResponseLayers
from sg_utils import make_choice_from_list

gi.require_version("Gimp", "3.0")
gi.require_version("GimpUi", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import GdkPixbuf, Gimp, GimpUi, GLib, GObject, Gtk, Pango


@dataclass(frozen=True)
class GenerationRequest:
    image: Gimp.Image
    values: dict[str, Any]
    source: GenerationSource
    payload: dict[str, Any]
    api: ApiClient

    def run(self, stop: Event) -> dict[str, Any] | None:
        if stop.is_set():
            return None
        self.api.post("/sdapi/v1/options", {"sd_model_checkpoint": self.values["sd_model_checkpoint"]})
        if stop.is_set():
            return None
        endpoint = "/sdapi/v1/txt2img" if self.values["generation_mode"] == "txt2img" else "/sdapi/v1/img2img"
        return self.api.post(endpoint, self.payload)

    def insert(self, response: dict[str, Any]) -> int:
        if not self.image.is_valid():
            raise ValueError(_("Target image closed; task finished"))
        self.image.undo_group_start()
        try:
            layers = ResponseLayers(
                self.image, response, {"skip_annotator_layers": self.values["cn_skip_annotator_layers"]},
            )
            if self.values["generation_mode"] == "txt2img":
                x1, y1, x2, y2 = self.source.selection_bounds
                layers.resize(x2 - x1, y2 - y1, strategy=self.values["insert_mode"]).translate((x1, y1))
                layers.addSelectionAsMask(self.source.selection)
            else:
                layers.translate(self.source.offset)
        finally:
            self.image.undo_group_end()
        Gimp.displays_flush()
        return min(len(response["images"]), len(json.loads(response["info"])["all_seeds"]))


class GenerationPluginBase(PluginBase):
    initial_mode: str
    sensitivity_mask = (
        Gimp.ProcedureSensitivityMask.DRAWABLE | Gimp.ProcedureSensitivityMask.DRAWABLES
        | Gimp.ProcedureSensitivityMask.NO_DRAWABLES
    )

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

    def collect_values(self, config: Gimp.ProcedureConfig) -> dict[str, Any]:
        values = {name: config.get_property(name) for name in GENERATION_PARAMETERS}
        values["seed"] = integer_seed(values["seed"])
        return values

    def validate_parameters(self, procedure: Gimp.Procedure, values: dict[str, Any]) -> None:
        config = procedure.create_config()
        for name in GENERATION_PARAMETERS:
            value = values[name]
            spec = procedure.find_argument(name.replace("_", "-"))
            expected_type = type(config.get_property(name))
            valid_type = type(value) in (int, float) if expected_type is float else type(value) is expected_type
            if not valid_type:
                raise ValueError(_("Invalid generation field: {field}").format(field=name))
            if expected_type in (int, float) and (
                not math.isfinite(value) or not spec.minimum <= value <= spec.maximum
            ):
                raise ValueError(_("Invalid generation field: {field}").format(field=name))
            if (
                expected_type is str and name not in ("prompt", "negative_prompt")
                and not Gimp.param_spec_choice_get_choice(spec).is_valid(value)
            ):
                raise ValueError(_("Unavailable generation option: {field} = {value}").format(field=name, value=value))
        integer_seed(values["seed"])
        validate_dimensions(values["width"], values["height"])

    def read_parameters(self, procedure: Gimp.Procedure, text: str) -> dict[str, Any]:
        defaults = self.collect_values(procedure.create_config())
        values = parse_generation(text, defaults)
        self.validate_parameters(procedure, values)
        return values

    def main(
        self, procedure: Gimp.Procedure, run_mode: Gimp.RunMode, image: Gimp.Image,
        drawables: list[Gimp.Drawable], config: Gimp.ProcedureConfig, data: Any,
    ) -> Gimp.ProcedureReturn:
        if run_mode == Gimp.RunMode.INTERACTIVE:
            from sg_plugins.panel import run_panel

            return run_panel(self, procedure, image, mode=self.initial_mode)
        try:
            values = self.collect_values(config)
            self.generate(image, config, values)
            return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())
        except (requests.RequestException, ValueError, OSError) as error:
            Gimp.message(str(error))
            return procedure.new_return_values(Gimp.PDBStatusType.CALLING_ERROR, GLib.Error(message=str(error)))
        finally:
            Gimp.progress_end()

    def prepare_request(
        self, image: Gimp.Image, config: Gimp.ProcedureConfig, values: dict[str, Any],
        source: GenerationSource | None = None,
    ) -> GenerationRequest:
        mode = values["generation_mode"]
        if source is None:
            source = GenerationSource.capture(image, mode)
        problem = source.problem(mode, values["invert_mask"])
        if problem:
            raise ValueError(problem)
        x1, y1, x2, y2 = source.selection_bounds
        size = x2 - x1, y2 - y1
        data = build_request(
            values, self.settings.get("prompt"), self.settings.get("negative_prompt"), size,
        )
        cache_enabled = bool(self.settings.get("cache_tobase64", True))
        if mode != "txt2img":
            data["init_images"] = [cast(PixelSnapshot, source.pixels).to_base64(cache_enabled=cache_enabled)]
        if mode == "inpaint":
            data["mask"] = cast(PixelSnapshot, source.mask).to_base64(cache_enabled=cache_enabled)
        units = []
        for slot in (1, 2):
            if values[f"cn{slot}_enabled"]:
                layer = config.get_property(f"cn{slot}_layer")
                if layer is None or layer.get_image() != image:
                    raise ValueError(_("Select a ControlNet input layer from the current image"))
                unit = {name: values[f"cn{slot}_{name}"] for name in CONTROLNET_PARAMETERS}
                unit["resize_mode"] = CONTROLNET_RESIZE_MODES.index(unit["resize_mode"])
                unit["control_mode"] = CONTROL_MODES.index(unit["control_mode"])
                unit["image"] = PixelSnapshot.read(layer).to_base64(cache_enabled=cache_enabled)
                if layer.get_mask() is not None:
                    unit["mask_image"] = PixelSnapshot.read_mask(layer.get_mask()).to_base64(
                        cache_enabled=cache_enabled,
                    )
                units.append(unit)
        if units:
            data["alwayson_scripts"] = {"controlnet": {"args": units}}
        return GenerationRequest(image, values, source, data, self.api)

    def generate(
        self, image: Gimp.Image, config: Gimp.ProcedureConfig, values: dict[str, Any],
        source: GenerationSource | None = None,
    ) -> None:
        request = self.prepare_request(image, config, values, source)
        Gimp.progress_init(_("Generating image"))
        with ThreadPoolExecutor(max_workers=1) as executor:
            pending = executor.submit(request.run, Event())
            try:
                while not wait((pending,), timeout=2).done:
                    progress = self.api.get("/sdapi/v1/progress", params={"skip_current_image": "true"}, timeout=5)
                    Gimp.progress_update(progress["progress"])
                    Gimp.progress_set_text(_("Progress: {progress}%, ETA: {eta}s").format(
                        progress=round(progress["progress"] * 100, 2), eta=round(progress["eta_relative"]),
                    ))
            except requests.RequestException as error:
                Gimp.message(str(error))
            response = pending.result()
        Gimp.progress_set_text(_("Inserting layers from response"))
        request.insert(cast(dict[str, Any], response))


class GenerationDialog:
    def __init__(
        self, plugin: GenerationPluginBase, procedure: Gimp.Procedure, config: Gimp.ProcedureConfig,
        image: Gimp.Image | None, lora_catalog: LoraCatalog, *,
        refresh_on_focus: bool = True,
    ) -> None:
        self.plugin = plugin
        self.procedure = procedure
        self.config = config
        self.image = image
        self.source_mode = ""
        self.source_error = ""
        self.source: GenerationSource | None = None
        self.ready = False
        self.busy = False
        self.file_path = ""
        self.settings_image = ""
        self.pending_parameters: dict[str, Any] = {}
        self.dialog = GimpUi.ProcedureDialog.new(procedure, config, _("GimpFusion generation"))
        self.dialog.set_ok_label(_("Generate"))
        for name in (
            "generation_mode", "sd_model_checkpoint", "sampler_index", "resize_mode", "insert_mode",
            "inpainting_fill",
            *(f"cn{slot}_{name}" for slot in (1, 2) for name in ("module", "model", "resize_mode", "control_mode")),
        ):
            combo = self.dialog.get_widget(name, Gtk.ComboBox.__gtype__).get_widget()
            for renderer in combo.get_cells():
                if isinstance(renderer, Gtk.CellRendererText):
                    renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
                    renderer.set_property("max-width-chars", 24)
        content = self.dialog.get_content_area()
        settings_buttons = next(child for child in content.get_children() if isinstance(child, Gtk.ButtonBox))
        settings_buttons.set_no_show_all(True)
        settings_buttons.hide()
        self.root = root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        content.pack_start(root, True, True, 0)
        self.save_button = Gtk.Button(label=_("Save file"))
        self.save_as_button = Gtk.Button(label=_("Save file as"))
        self.save_image_button = Gtk.Button(label=_("Save to image"))
        self.load_image_button = Gtk.Button(label=_("Load from image"))
        settings_buttons = Gtk.Grid(column_spacing=6, row_spacing=6, column_homogeneous=True)
        for index, (button, callback) in enumerate((
            (Gtk.Button(label=_("Load file")), self.load_file),
            (self.save_button, self.save_current),
            (self.save_as_button, self.save_as),
            (self.save_image_button, self.save_to_image),
            (self.load_image_button, self.load_from_image),
        )):
            settings_buttons.attach(button, index % 2, index // 2, 1, 1)
            button.get_child().set_line_wrap(True)
            button.get_child().set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
            button.get_child().set_max_width_chars(16)
            button.connect("clicked", callback)
        self.current_label = Gtk.Label(xalign=0)
        root.pack_start(self.current_label, False, False, 0)
        self.error_label = Gtk.Label(xalign=0, wrap=True)
        root.pack_start(self.error_label, False, False, 0)
        self.dimension_label = Gtk.Label(xalign=0, wrap=True)
        self.dimension_label.set_no_show_all(True)
        root.pack_start(self.dimension_label, False, False, 0)
        self.input_label = Gtk.Label(xalign=0, wrap=True)
        root.pack_start(self.input_label, False, False, 0)
        for label in (self.error_label, self.dimension_label, self.input_label):
            label.set_no_show_all(True)
            label.connect("notify::label", lambda current, _property: current.set_visible(bool(current.get_text())))
        root.add(self.dialog.fill_box("mode_model", ["generation_mode", "sd_model_checkpoint"]))
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_overlay_scrolling(False)
        scroll.set_min_content_height(48)
        root.pack_start(scroll, True, True, 0)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        scroll.add(body)
        settings_actions = Gtk.Expander(label=_("Generation settings"))
        settings_actions.add(settings_buttons)
        body.add(settings_actions)
        source_frame = Gtk.Frame(label=_("Input source"))
        source_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=8)
        source_frame.add(source_box)
        self.source_preview = Gtk.Image()
        source_box.pack_start(self.source_preview, False, False, 0)
        self.source_label = Gtk.Label(xalign=0, wrap=True, selectable=True)
        source_box.pack_start(self.source_label, True, True, 0)
        body.add(source_frame)
        add_textarea_to_container(procedure, config, "prompt", body)
        add_textarea_to_container(procedure, config, "negative-prompt", body)
        lora_frame = Gtk.Expander(label="LoRA")
        self.loras = LoraSelector(plugin.api, config, lora_catalog)
        self.loras.set_border_width(8)
        lora_frame.add(self.loras)
        body.add(lora_frame)
        seed_widget = self.dialog.get_widget("seed", GimpUi.LabelSpin.__gtype__)
        seed_widget.get_spin_button().set_digits(0)
        seed_widget.get_spin_button().set_increments(1, 100)
        self.dimension_spins = []
        for name in ("width", "height"):
            entry = self.dialog.get_scale_entry(name, 1)
            entry.set_increments(8, 64)
            entry.get_range().connect("change-value", self.change_dimension)
            self.dimension_spins.append(entry.get_spin_button())
        cfg_spin = self.dialog.get_widget("cfg_scale", GimpUi.LabelSpin.__gtype__).get_spin_button()
        cfg_spin.set_digits(2)
        cfg_spin.set_increments(0.5, 1)
        parameters = Gtk.Expander(label=_("Generation parameters"), expanded=True)
        common = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        parameters.add(common)
        body.add(parameters)
        self.width_box = self.dialog.fill_box("width_box", ["width"])
        self.height_box = self.dialog.fill_box("height_box", ["height"])
        common.add(self.width_box)
        common.add(self.height_box)
        for name in ("seed", "steps", "cfg_scale", "batch_size"):
            common.add(self.dialog.fill_box(name + "_box", [name]))
        common.add(self.dialog.fill_box("common_options", ["sampler_index", "restore_faces", "tiling"]))
        self.padding_widget = self.dialog.get_scale_entry("inpaint_full_res_padding", 1)
        self.padding_widget.set_increments(4, 32)
        self.mode_boxes = {
            "txt2img": self.dialog.fill_box("txt_options", ["insert_mode"]),
            "image": self.dialog.fill_box("image_options", ["denoising_strength", "resize_mode", "mask_blur"]),
            "inpaint": self.dialog.fill_box(
                "inpaint_options", ["invert_mask", "inpainting_fill", "inpaint_full_res_padding"],
            ),
        }
        area = GimpUi.prop_boolean_radio_frame_new(
            config, "inpaint-full-res", _("Inpaint area"), _("Only masked"), _("Whole picture"),
        )
        self.mode_boxes["inpaint"].pack_start(area, False, False, 0)
        self.mode_boxes["inpaint"].reorder_child(area, 0)
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
        for name in GENERATION_PARAMETERS:
            if name not in (
                "prompt", "negative_prompt", "restore_faces", "tiling", "inpaint_full_res", "invert_mask",
                "cn1_enabled", "cn2_enabled", "cn_skip_annotator_layers",
            ):
                label = self.dialog.get_widget(name, Gtk.Widget.__gtype__).get_label()
                label.set_line_wrap(True)
                label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
                label.set_max_width_chars(10)
        for label in (
            self.current_label, self.error_label, self.dimension_label, self.input_label,
            self.source_label, self.size_label,
        ):
            label.set_line_wrap(True)
            label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
            label.set_max_width_chars(32)
        root.show_all()
        self.dialog.resize(860, 760)
        config.connect("notify", self.refresh_mode)
        if refresh_on_focus:
            self.dialog.connect("focus-in-event", self.refresh_source)
        for spin in self.dimension_spins:
            spin.connect("changed", self.refresh_mode)
        self.refresh_settings_label()

    def change_dimension(self, slider: Gtk.Range, _scroll: Gtk.ScrollType, value: float) -> bool:
        slider.set_value(8 * round(value / 8))
        return True

    def refresh_settings_label(self) -> None:
        if self.file_path:
            label = _("File: {name}").format(name=Path(self.file_path).name)
        elif self.settings_image:
            label = _("Settings from image: {name}").format(name=self.settings_image)
        else:
            label = _("Unsaved parameters")
        self.current_label.set_text(label)
        self.current_label.set_tooltip_text(self.file_path or label)
        self.refresh_mode()

    def refresh_mode(self, *_args: Any) -> None:
        mode = self.config.get_property("generation_mode")
        if mode != self.source_mode:
            self.refresh_source()
            return
        self.mode_boxes["txt2img"].set_visible(mode == "txt2img")
        self.mode_boxes["image"].set_visible(mode != "txt2img")
        self.mode_boxes["inpaint"].set_visible(mode == "inpaint")
        self.padding_widget.set_sensitive(self.config.get_property("inpaint_full_res"))
        use_dimensions = not (
            mode == "txt2img" and self.config.get_property("insert_mode") == "Use selection size"
        )
        self.width_box.set_sensitive(use_dimensions)
        self.height_box.set_sensitive(use_dimensions)
        selection_bounds = self.source.selection_bounds if self.source is not None else (0, 0, 0, 0)
        x1, y1, x2, y2 = selection_bounds
        values = {name: self.config.get_property(name) for name in (
            "generation_mode", "insert_mode", "width", "height", "inpaint_full_res",
        )}
        dimension_error = ""
        try:
            values["width"], values["height"] = (int(spin.get_text()) for spin in self.dimension_spins)
            validate_dimensions(values["width"], values["height"])
        except ValueError:
            dimension_error = _("Width and height must be positive multiples of 8")
        valid_dimensions = not dimension_error
        self.save_button.set_sensitive(valid_dimensions)
        self.save_as_button.set_sensitive(valid_dimensions)
        has_image = self.image is not None and self.image.is_valid()
        self.save_image_button.set_sensitive(has_image and valid_dimensions)
        self.load_image_button.set_sensitive(has_image)
        width, height = generation_size(values, (x2 - x1, y2 - y1))
        if not use_dimensions:
            dimension_error = ""
            try:
                validate_dimensions(width, height)
            except ValueError as error:
                dimension_error = str(error)
        self.dimension_label.set_text(dimension_error)
        self.dimension_label.set_visible(bool(dimension_error))
        problem = self.source_error
        if self.source is not None:
            problem = problem or self.source.problem(mode, self.config.get_property("invert_mask"))
        self.input_label.set_text(problem)
        self.ready = not dimension_error and not problem
        self.dialog.set_response_sensitive(Gtk.ResponseType.OK, self.ready and not self.busy)
        if dimension_error or self.source is None:
            self.size_label.set_text("")
            return
        source_size = (
            (self.source.pixels.width, self.source.pixels.height)
            if self.source.pixels is not None else self.source.image_size
        )
        area_width, area_height = insertion_size(
            values, (x2 - x1, y2 - y1), source_size,
        )
        self.size_label.set_text(_("Request: {width} x {height}; insertion area: {area_width} x {area_height}").format(
            width=width, height=height, area_width=area_width, area_height=area_height,
        ))

    def refresh_source(self, *_args: Any) -> bool:
        self.source_mode = self.config.get_property("generation_mode")
        self.config.freeze_notify()
        for name in MODE_PARAMETERS[self.source_mode]:
            if name in self.pending_parameters:
                self.config.set_property(name, self.pending_parameters.pop(name))
        self.config.thaw_notify()
        if self.image is None:
            self.source = None
            self.source_error = _("Select a target image")
            self.source_label.set_text(self.source_error)
            self.source_preview.clear()
            self.refresh_mode()
            return False
        try:
            self.source = GenerationSource.capture(self.image, self.source_mode)
        except ValueError as error:
            self.source = None
            self.source_error = str(error)
            self.source_label.set_text(self.source_error)
            self.source_preview.clear()
            self.refresh_mode()
            return False
        self.source_error = ""
        source = self.source
        lines = [_("Target image: {name}").format(name=source.image_name)]
        x1, y1, x2, y2 = source.selection_bounds
        lines.append(_("Selection: ({x}, {y}), {width} x {height}").format(
            x=x1, y=y1, width=x2 - x1, height=y2 - y1,
        ) if source.selection is not None else _("Selection: whole image"))
        self.source_preview.clear()
        if source.pixels is not None:
            pixels = source.pixels
            lines.append(_("Source layer: {name}").format(name=source.layer_name))
            lines.append(_("Source: {width} x {height}; offset: ({x}, {y})").format(
                width=pixels.width, height=pixels.height, x=source.offset[0], y=source.offset[1],
            ))
            scale = min(128 / pixels.width, 96 / pixels.height, 1)
            self.source_preview.set_from_pixbuf(pixels.pixbuf().scale_simple(
                max(1, int(pixels.width * scale)), max(1, int(pixels.height * scale)), GdkPixbuf.InterpType.BILINEAR,
            ))
        if self.source_mode == "inpaint":
            mask_name = {"selection": _("Current selection"), "layer": _("Source layer mask"), "": _("Create a mask")}
            lines.append(_("Mask source: {name}").format(name=mask_name[source.mask_source]))
        self.source_label.set_text("\n".join(lines))
        self.refresh_mode()
        return False

    def collect_values(self) -> dict[str, Any]:
        return {**self.plugin.collect_values(self.config), **self.pending_parameters}

    def load_parameters(self, values: dict[str, Any]) -> None:
        mode = self.config.get_property("generation_mode")
        self.pending_parameters = {
            name: values[name] for name in MODE_SPECIFIC_PARAMETERS if name not in MODE_PARAMETERS[mode]
        }
        self.config.freeze_notify()
        for name in (*COMMON_PARAMETERS, *MODE_PARAMETERS[mode]):
            self.config.set_property(name, values[name])
        self.config.thaw_notify()
        self.refresh_source()

    def choose_file(self, action: Gtk.FileChooserAction) -> str | None:
        saving = action == Gtk.FileChooserAction.SAVE
        chooser = Gtk.FileChooserNative.new(
            _("Save generation settings") if saving else _("Load generation settings"),
            self.root.get_toplevel(), action, _("Save") if saving else _("Open"), _("Cancel"),
        )
        file_filter = Gtk.FileFilter()
        file_filter.set_name(_("Generation settings (*.txt)"))
        file_filter.add_pattern("*.txt")
        chooser.add_filter(file_filter)
        if self.file_path:
            chooser.set_current_folder(str(Path(self.file_path).parent))
        if saving:
            chooser.set_do_overwrite_confirmation(True)
            chooser.set_current_name(Path(self.file_path).name if self.file_path else "generation.txt")
        elif self.file_path:
            chooser.set_filename(self.file_path)
        try:
            return chooser.get_filename() if chooser.run() == Gtk.ResponseType.ACCEPT else None
        finally:
            chooser.destroy()

    def load_file(self, *_args: Any) -> None:
        path = self.choose_file(Gtk.FileChooserAction.OPEN)
        if path is None:
            return
        try:
            values = self.plugin.read_parameters(self.procedure, Path(path).read_text(encoding="utf-8-sig"))
        except (configparser.Error, KeyError, ValueError, OSError) as error:
            self.error_label.set_text(str(error))
            return
        self.load_parameters(values)
        self.file_path = path
        self.settings_image = ""
        self.error_label.set_text("")
        self.refresh_settings_label()

    def save_current(self, *_args: Any) -> None:
        if self.file_path:
            self.write_file(self.file_path)
        else:
            self.save_as()

    def write_file(self, path: str) -> None:
        try:
            values = self.collect_values()
            validate_dimensions(values["width"], values["height"])
            Path(path).write_text(serialize_generation(values), encoding="utf-8")
        except (ValueError, OSError) as error:
            self.error_label.set_text(str(error))
            return
        self.file_path = path
        self.settings_image = ""
        self.error_label.set_text("")
        self.refresh_settings_label()

    def save_as(self, *_args: Any) -> None:
        path = self.choose_file(Gtk.FileChooserAction.SAVE)
        if path is None:
            return
        if not Path(path).suffix:
            path += ".txt"
        self.write_file(path)

    def save_to_image(self, *_args: Any) -> None:
        try:
            values = self.collect_values()
            validate_dimensions(values["width"], values["height"])
            parasite = Gimp.Parasite.new(
                GENERATION_PARASITE, Gimp.PARASITE_PERSISTENT | Gimp.PARASITE_UNDOABLE,
                serialize_generation(values).encode("utf-8"),
            )
            if not cast(Gimp.Image, self.image).attach_parasite(parasite):
                raise ValueError(_("Could not save generation settings to the image"))
            self.error_label.set_text("")
            Gimp.displays_flush()
        except (ValueError, GLib.Error) as error:
            self.error_label.set_text(str(error))

    def load_from_image(self, *_args: Any) -> None:
        image = cast(Gimp.Image, self.image)
        parasite = image.get_parasite(GENERATION_PARASITE)
        if parasite is None:
            self.error_label.set_text(_("The current image has no generation settings"))
            return
        try:
            values = self.plugin.read_parameters(self.procedure, bytes(parasite.get_data()).decode("utf-8"))
        except (configparser.Error, KeyError, ValueError) as error:
            self.error_label.set_text(str(error))
            return
        self.load_parameters(values)
        self.file_path = ""
        self.settings_image = image.get_name()
        self.error_label.set_text("")
        self.refresh_settings_label()

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
            self.plugin.validate_parameters(self.procedure, values)
            for field in CONTROLNET_PARAMETERS:
                self.config.set_property(f"cn{slot}_{field}", values[f"cn{slot}_{field}"])
            self.error_label.set_text("")
        except (KeyError, TypeError, ValueError) as error:
            self.error_label.set_text(str(error))
