"""Persistent generation window and its main-thread task lifecycle."""

from __future__ import annotations

import subprocess

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event
from typing import Any, cast

import gi
import requests

from sg_generation import GENERATION_MODES, GENERATION_PARAMETERS
from sg_i18n import _
from sg_loras import LoraCatalog
from sg_notifications import notify_generation_finished
from sg_plugins.generation_base import GenerationDialog, GenerationPluginBase, GenerationRequest
from sg_structures import ApiClient
from sg_utils import fetch_stablediffusion_options, make_choice_from_list

gi.require_version("Gimp", "3.0")
gi.require_version("GimpUi", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gimp, GimpUi, GLib, GObject, Gtk, Pango

PANEL_PROCEDURE = "stable-gimpfusion-panel"
PANEL_COMMAND = "stable-gimpfusion-panel-command"
GENERATE_CURRENT_PROCEDURE = "stable-gimpfusion-generate-current"


def run_panel(
    plugin: GenerationPluginBase, procedure: Gimp.Procedure, image: Gimp.Image | None, *,
    action: str = "present", mode: str = "current",
) -> Gimp.ProcedureReturn:
    pdb = Gimp.get_pdb()
    if pdb.procedure_exists(PANEL_COMMAND):
        command = pdb.lookup_procedure(PANEL_COMMAND)
        arguments = command.create_config()
        arguments.set_property("action", action)
        arguments.set_property("image", image)
        arguments.set_property("mode", mode)
        return command.run(arguments)
    GimpUi.init(PANEL_PROCEDURE)
    session = PanelSession(plugin, procedure, image, action=action, mode=mode)
    temporary = Gimp.Procedure.new(
        procedure.get_plug_in(), PANEL_COMMAND, Gimp.PDBProcType.TEMPORARY, session.command, None,
    )
    temporary.add_choice_argument(
        "action", "Action", "Action", make_choice_from_list(["present", "set-target", "generate", "close"]),
        "present", GObject.ParamFlags.READWRITE,
    )
    temporary.add_image_argument("image", "Image", "Image", True, GObject.ParamFlags.READWRITE)
    temporary.add_choice_argument(
        "mode", _("Generation mode"), _("Generation mode"),
        make_choice_from_list(["current", *GENERATION_MODES]), "current", GObject.ParamFlags.READWRITE,
    )
    plug_in = procedure.get_plug_in()
    plug_in.add_temp_procedure(temporary)
    plug_in.persistent_enable()
    session.start()
    Gtk.main()
    plug_in.remove_temp_procedure(PANEL_COMMAND)
    return procedure.new_return_values(
        Gimp.PDBStatusType.EXECUTION_ERROR if session.failed else Gimp.PDBStatusType.SUCCESS, GLib.Error(),
    )


class PanelPlugin(GenerationPluginBase):
    menu_path = "<Image>/GimpFusion"
    menu_label = _("Open generation panel")
    description = _("Open the persistent GimpFusion generation window")
    sensitivity_mask = Gimp.ProcedureSensitivityMask.ALWAYS
    initial_mode = "txt2img"
    initial_action = "present"

    def add_arguments(self, procedure: Gimp.Procedure) -> None:
        """ImageProcedure supplies the run mode, image and drawables."""

    def main(
        self, procedure: Gimp.Procedure, run_mode: Gimp.RunMode, image: Gimp.Image | None,
        drawables: list[Gimp.Drawable], config: Gimp.ProcedureConfig, data: Any,
    ) -> Gimp.ProcedureReturn:
        return run_panel(self, procedure, image, action=self.initial_action)


class GenerateCurrentPlugin(PanelPlugin):
    menu_label = _("Generate with current parameters")
    description = _("Generate on the current image using the panel mode and parameters")
    sensitivity_mask = GenerationPluginBase.sensitivity_mask
    initial_action = "generate"


class PanelSession:
    def __init__(
        self, plugin: GenerationPluginBase, procedure: Gimp.Procedure, image: Gimp.Image | None, *,
        action: str = "present", mode: str = "current",
    ) -> None:
        self.plugin = plugin
        self.procedure = procedure
        self.image = image
        self.requested_mode = mode
        self.pending_generate = action == "generate"
        self.editor: GenerationDialog | None = None
        self.task: GenerationRequest | None = None
        self.progress_future: Future[Any] | None = None
        self.interrupt_sent = False
        self.progress_timer = 0
        self.closing = False
        self.failed = False
        self.stop = Event()
        self.pending: set[Future[Any]] = set()
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="gimpfusion-http")
        self.state = plugin.settings.get("panel_state")
        self.window = Gtk.Window(title=_("GimpFusion generation"))
        self.window.set_type_hint(Gdk.WindowTypeHint.NORMAL)
        geometry = Gdk.Geometry()
        geometry.min_width, geometry.min_height = 360, 480
        self.window.set_geometry_hints(None, geometry, Gdk.WindowHints.MIN_SIZE)
        self.window.set_default_size(self.state["width"], self.state["height"])
        self.window.add(Gtk.Label(label=_("Connecting to Forge")))
        self.window.connect("delete-event", self.close)
        self.window.show_all()

    def submit(self, function: Callable[..., Any], callback: Callable[[Future[Any]], None], *args: Any) -> Future[Any]:
        future = self.executor.submit(function, *args)
        self.pending.add(future)
        future.add_done_callback(lambda completed: GLib.idle_add(self.deliver, completed, callback))
        return future

    def deliver(self, future: Future[Any], callback: Callable[[Future[Any]], None]) -> bool:
        self.pending.remove(future)
        try:
            callback(future)
        finally:
            if self.closing and not self.pending:
                self.finish_close()
        return GLib.SOURCE_REMOVE

    def start(self) -> None:
        api = ApiClient(self.plugin.settings.get("api_base"), timeout=5)
        self.submit(self.read_backend, self.connected, api)

    @staticmethod
    def read_backend(api: ApiClient) -> tuple[dict[str, Any], LoraCatalog]:
        options = fetch_stablediffusion_options(api)
        catalog = LoraCatalog(
            api.get("/sdapi/v1/loras"), options["lora_preferred_name"],
            options["extra_networks_default_multiplier"], options["extra_networks_add_text_separator"],
        )
        return options, catalog

    def connected(self, future: Future[Any]) -> None:
        try:
            options, catalog = future.result()
        except (requests.RequestException, ValueError, OSError) as error:
            self.failed = True
            Gimp.message(str(error))
            self.closing = True
            return
        if self.closing:
            return
        try:
            self.create_editor(options, catalog)
            if self.pending_generate:
                self.pending_generate = False
                self.generate()
        except (ValueError, OSError, GLib.Error) as error:
            self.failed = True
            Gimp.message(str(error))
            self.closing = True

    def create_editor(self, options: dict[str, Any], catalog: LoraCatalog) -> None:
        self.plugin.settings.save(options)
        parameters = Gimp.ImageProcedure.new(
            self.procedure.get_plug_in(), "stable-gimpfusion-panel-settings", Gimp.PDBProcType.PLUGIN,
            GenerationPluginBase.main.__get__(self.plugin), None,
        )
        GenerationPluginBase.add_arguments(self.plugin, parameters)
        configuration = parameters.create_config()
        saved = self.state["parameters"]
        if saved is not None:
            self.plugin.validate_parameters(parameters, saved)
            for name in GENERATION_PARAMETERS:
                configuration.set_property(name, saved[name])
        if self.requested_mode != "current":
            configuration.set_property("generation_mode", self.requested_mode)
        self.editor = editor = GenerationDialog(self.plugin, parameters, configuration, self.image, catalog)
        editor.file_path = self.state.get("file_path", "")
        editor.refresh_settings_label()
        self.window.get_child().destroy()
        editor.dialog.get_content_area().remove(editor.root)
        editor.root.set_border_width(12)
        self.window.add(editor.root)
        self.targets = Gtk.ComboBoxText()
        for renderer in self.targets.get_cells():
            renderer.set_property("ellipsize", Pango.EllipsizeMode.END)
            renderer.set_property("max-width-chars", 24)
        self.target_handler = self.targets.connect("changed", self.select_target)
        self.targets.connect("notify::popup-shown", self.target_popup)
        target_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        target_box.add(Gtk.Label(label=_("Target image"), xalign=0))
        target_box.add(self.targets)
        editor.root.pack_start(target_box, False, False, 0)
        editor.root.reorder_child(target_box, 0)
        self.progress = Gtk.ProgressBar(show_text=True)
        self.status = Gtk.Label(xalign=0, wrap=True, max_width_chars=32)
        self.status.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.status.set_ellipsize(Pango.EllipsizeMode.END)
        self.status.set_lines(3)
        self.status.bind_property("label", self.status, "tooltip-text", GObject.BindingFlags.SYNC_CREATE)
        self.status.set_no_show_all(True)
        self.status.connect("notify::label", lambda label, _property: label.set_visible(bool(label.get_text())))
        self.notification = Gtk.CheckButton(
            label=_("Show a system notification after generation"), active=self.state["notification_toast"],
        )
        self.notification.get_child().set_line_wrap(True)
        self.notification.get_child().set_max_width_chars(30)
        for widget in (self.progress, self.status, self.notification):
            editor.root.pack_start(widget, False, False, 0)
        buttons = Gtk.ButtonBox(spacing=6, layout_style=Gtk.ButtonBoxStyle.END)
        generate = Gtk.Button(label=_("Generate"), can_default=True)
        close = Gtk.Button(label=_("Close"))
        buttons.add(generate)
        buttons.add(close)
        editor.root.pack_start(buttons, False, False, 0)
        self.window.set_default(generate)
        generate.connect("clicked", self.generate)
        close.connect("clicked", self.close)
        editor.dialog.get_widget_for_response(Gtk.ResponseType.OK).bind_property(
            "sensitive", generate, "sensitive", GObject.BindingFlags.SYNC_CREATE,
        )
        editor.loras.refresh_button.connect("clicked", self.refresh_loras)
        self.window.connect("focus-in-event", self.refresh_targets)
        self.refresh_targets()
        self.window.show_all()
        editor.refresh_mode()

    def target_popup(self, combo: Gtk.ComboBox, _property: GObject.ParamSpec) -> None:
        if combo.get_property("popup-shown"):
            self.refresh_targets()

    def refresh_targets(self, *_args: Any) -> bool:
        self.targets.handler_block(self.target_handler)
        self.targets.remove_all()
        for image in Gimp.get_images():
            self.targets.append(str(image.get_id()), image.get_name())
        if self.image is not None and not self.image.is_valid():
            self.image = None
        self.targets.set_active_id(str(self.image.get_id()) if self.image is not None else None)
        self.targets.handler_unblock(self.target_handler)
        editor = cast(GenerationDialog, self.editor)
        editor.image = self.image
        editor.refresh_source()
        return False

    def select_target(self, combo: Gtk.ComboBoxText) -> None:
        identifier = combo.get_active_id()
        self.set_target(Gimp.Image.get_by_id(int(identifier)) if identifier is not None else None)

    def set_target(self, image: Gimp.Image | None) -> None:
        changed = image != self.image
        self.image = image
        if self.editor is not None:
            if changed:
                self.editor.config.freeze_notify()
                for slot in (1, 2):
                    self.editor.config.set_property(f"cn{slot}_layer", None)
                self.editor.config.thaw_notify()
            self.refresh_targets()

    def command(self, procedure: Gimp.Procedure, config: Gimp.ProcedureConfig, _data: Any) -> Gimp.ProcedureReturn:
        action = config.get_property("action")
        if action == "close":
            self.close()
        elif self.closing:
            return procedure.new_return_values(Gimp.PDBStatusType.CANCEL, GLib.Error(message=_("Closing panel")))
        elif action == "generate" and (self.task is not None or self.pending_generate):
            return procedure.new_return_values(
                Gimp.PDBStatusType.CANCEL, GLib.Error(message=_("Generation is busy or needs input")),
            )
        else:
            image, mode = config.get_property("image"), config.get_property("mode")
            if image is not None or action == "set-target":
                self.set_target(image)
            if mode != "current":
                self.requested_mode = mode
                if self.editor is not None:
                    self.editor.config.set_property("generation_mode", mode)
            if action == "generate" and self.editor is None:
                self.pending_generate = True
            elif action == "generate" and not self.generate():
                return procedure.new_return_values(
                    Gimp.PDBStatusType.CANCEL, GLib.Error(message=_("Generation is busy or needs input")),
                )
            elif action != "generate":
                if self.editor is not None and image is None and action != "set-target":
                    self.refresh_targets()
                self.window.present()
        return procedure.new_return_values(Gimp.PDBStatusType.SUCCESS, GLib.Error())

    def generate(self, *_args: Any) -> bool:
        if self.closing or self.editor is None or self.task is not None:
            return False
        editor = self.editor
        try:
            self.plugin.settings.reload()
            self.plugin.api = ApiClient(self.plugin.settings.get("api_base"))
            editor.refresh_source()
            if not editor.ready:
                return False
            values = editor.collect_values()
            self.task = self.plugin.prepare_request(
                cast(Gimp.Image, editor.image), editor.config, values, editor.source,
            )
        except (ValueError, OSError) as error:
            self.status.set_text(str(error))
            return False
        self.stop = Event()
        self.interrupt_sent = False
        self.progress.set_fraction(0)
        self.progress.set_text(_("Generating image"))
        self.status.set_text(_("Generating image"))
        editor.busy = True
        editor.refresh_mode()
        self.submit(self.task.run, self.generated, self.stop)
        self.progress_timer = GLib.timeout_add_seconds(2, self.poll_progress)
        return True

    def poll_progress(self) -> bool:
        if self.task is None:
            self.progress_timer = 0
            return GLib.SOURCE_REMOVE
        if self.progress_future is None:
            api = ApiClient(self.task.api.base_url, timeout=5)
            self.progress_future = self.submit(self.read_progress, self.progress_received, api, self.task)
        return GLib.SOURCE_CONTINUE

    @staticmethod
    def read_progress(api: ApiClient, task: GenerationRequest) -> tuple[GenerationRequest, dict[str, Any]]:
        return task, api.get("/sdapi/v1/progress", params={"skip_current_image": "true"})

    def progress_received(self, future: Future[Any]) -> None:
        self.progress_future = None
        try:
            task, progress = cast(tuple[GenerationRequest, dict[str, Any]], future.result())
        except requests.RequestException as error:
            self.status.set_text(str(error))
            return
        if task is not self.task:
            return
        self.progress.set_fraction(progress["progress"])
        self.progress.set_text(_("Progress: {progress}%, ETA: {eta}s").format(
            progress=round(progress["progress"] * 100, 2), eta=round(progress["eta_relative"]),
        ))
        if self.closing and progress["state"]["job_count"] != 0 and not self.interrupt_sent:
            self.interrupt_sent = True
            api = ApiClient(task.api.base_url, timeout=5)
            self.submit(api.post, self.interrupted, "/sdapi/v1/interrupt")

    def interrupted(self, future: Future[Any]) -> None:
        try:
            future.result()
        except requests.RequestException as error:
            self.status.set_text(str(error))

    def generated(self, future: Future[Any]) -> None:
        task = cast(GenerationRequest, self.task)
        self.task = None
        if self.progress_timer:
            GLib.source_remove(self.progress_timer)
            self.progress_timer = 0
        editor = cast(GenerationDialog, self.editor)
        editor.busy = self.closing
        try:
            response = future.result()
            if response is None:
                self.status.set_text(_("Generation interrupted"))
                self.progress.set_text(_("Generation interrupted"))
                return
            count = task.insert(response)
            if self.closing:
                self.status.set_text(_("Generation interrupted"))
                self.progress.set_text(_("Generation interrupted"))
            else:
                self.progress.set_fraction(1)
                self.progress.set_text(_("GimpFusion generation finished"))
                self.status.set_text(_("Inserted {count} candidates into {name}").format(
                    count=count, name=task.source.image_name,
                ))
                if count and self.notification.get_active():
                    self.submit(
                        notify_generation_finished, self.notified, _("GimpFusion generation finished"),
                        _("{name}: {count} candidates").format(name=task.source.image_name, count=count),
                    )
        except (requests.RequestException, ValueError, OSError, GLib.Error) as error:
            self.progress.set_text(_("Generation failed"))
            self.status.set_text(str(error))
        finally:
            editor.refresh_source()

    def notified(self, future: Future[Any]) -> None:
        try:
            future.result()
        except subprocess.CalledProcessError as error:
            self.status.set_text(_("Notification failed with exit code {code}").format(code=error.returncode))
        except subprocess.TimeoutExpired:
            self.status.set_text(_("Notification timed out"))
        except OSError as error:
            self.status.set_text(_("Notification failed: {error}").format(error=error))

    def refresh_loras(self, *_args: Any) -> None:
        editor = cast(GenerationDialog, self.editor)
        editor.loras.refresh_button.set_sensitive(False)
        self.submit(self.read_loras, self.loras_received, self.plugin.api, editor.loras.catalog)

    @staticmethod
    def read_loras(api: ApiClient, catalog: LoraCatalog) -> LoraCatalog:
        api.post("/sdapi/v1/refresh-loras")
        return LoraCatalog(
            api.get("/sdapi/v1/loras"), catalog.preferred_name, catalog.default_multiplier, catalog.separator,
        )

    def loras_received(self, future: Future[Any]) -> None:
        selector = cast(GenerationDialog, self.editor).loras
        selector.refresh_button.set_sensitive(True)
        try:
            selector.catalog = future.result()
        except requests.RequestException as error:
            selector.error_label.set_text(str(error))
            return
        selector.error_label.set_text("")
        selector.filter_catalog()

    def close(self, *_args: Any) -> bool:
        if self.closing:
            return True
        self.closing = True
        self.stop.set()
        if self.editor is not None:
            self.editor.busy = True
            self.editor.refresh_mode()
            self.status.set_text(_("Interrupting generation") if self.task is not None else _("Closing panel"))
            if self.task is not None:
                self.poll_progress()
        if not self.pending:
            self.finish_close()
        return True

    def finish_close(self) -> None:
        width, height = self.window.get_size()
        state = {**self.state, "width": width, "height": height}
        if self.editor is not None:
            state = {
                "width": width, "height": height,
                "parameters": self.editor.collect_values(), "file_path": self.editor.file_path,
                "notification_toast": self.notification.get_active(),
            }
        self.plugin.settings.save({"panel_state": state})
        self.executor.shutdown(wait=True)
        if self.editor is not None:
            self.editor.dialog.destroy()
        self.window.destroy()
        GLib.idle_add(Gtk.main_quit)
