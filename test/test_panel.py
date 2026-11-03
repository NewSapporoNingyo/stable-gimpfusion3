from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import unittest

from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

import gi

from sg_plugins.generation_base import GenerationDialog, GenerationPluginBase, GenerationRequest
from sg_plugins.img2img import Image2imagePlugin
from sg_plugins.inpainting import InpaintingPlugin
from sg_plugins.panel import PANEL_COMMAND, GenerateCurrentPlugin, PanelSession
from sg_plugins.txt2img import Txt2imagePlugin
from sg_sources import GenerationSource
from sg_structures import ApiClient, MyShelf

gi.require_version("Gimp", "3.0")
from gi.repository import Gimp


class PanelTests(unittest.TestCase):
    def request(self) -> GenerationRequest:
        source = GenerationSource("original", (64, 64), (8, 16, 40, 48), None, "", (0, 0), None, None, "")
        return GenerationRequest(
            MagicMock(), {"generation_mode": "txt2img", "sd_model_checkpoint": "model",
                          "cn_skip_annotator_layers": True, "insert_mode": "Resize to selection"},
            source, {"prompt": "snapshot"}, MagicMock(spec=ApiClient, base_url="http://example.test"),
        )

    def test_interactive_entries_forward_image_action_and_mode_to_existing_panel(self) -> None:
        for plugin_class, action, mode in (
            (Txt2imagePlugin, "present", "txt2img"),
            (Image2imagePlugin, "present", "img2img"),
            (InpaintingPlugin, "present", "inpaint"),
            (GenerateCurrentPlugin, "generate", "current"),
        ):
            with self.subTest(plugin=plugin_class.__name__), patch("sg_plugins.panel.Gimp.get_pdb") as get_pdb:
                plugin = plugin_class(MagicMock(), MagicMock())
                procedure, image = MagicMock(), MagicMock()
                command = get_pdb.return_value.lookup_procedure.return_value
                result = plugin.main(procedure, Gimp.RunMode.INTERACTIVE, image, [], MagicMock(), None)
                assert result is command.run.return_value
                get_pdb.return_value.procedure_exists.assert_called_once_with(PANEL_COMMAND)
                arguments = command.create_config.return_value
                assert arguments.set_property.call_args_list == [
                    (("action", action),), (("image", image),), (("mode", mode),),
                ]

    def test_first_shortcut_starts_one_persistent_session(self) -> None:
        plugin = GenerateCurrentPlugin(MagicMock(), MagicMock())
        procedure, image = MagicMock(), MagicMock()
        with (
            patch("sg_plugins.panel.Gimp.get_pdb") as get_pdb,
            patch("sg_plugins.panel.GimpUi.init"),
            patch("sg_plugins.panel.Gimp.Procedure.new") as temporary,
            patch("sg_plugins.panel.PanelSession") as session_class,
            patch("sg_plugins.panel.Gtk.main") as main,
        ):
            get_pdb.return_value.procedure_exists.return_value = False
            session_class.return_value.failed = False
            plugin.main(procedure, Gimp.RunMode.INTERACTIVE, image, [], MagicMock(), None)
        session_class.assert_called_once_with(plugin, procedure, image, action="generate", mode="current")
        procedure.get_plug_in.return_value.add_temp_procedure.assert_called_once_with(temporary.return_value)
        procedure.get_plug_in.return_value.persistent_enable.assert_called_once()
        session_class.return_value.start.assert_called_once()
        main.assert_called_once()
        procedure.get_plug_in.return_value.remove_temp_procedure.assert_called_once_with(PANEL_COMMAND)

    def test_script_run_modes_keep_using_supplied_parameters(self) -> None:
        plugin = Txt2imagePlugin(MagicMock(), MagicMock())
        for mode in (Gimp.RunMode.NONINTERACTIVE, Gimp.RunMode.WITH_LAST_VALS):
            with (
                self.subTest(mode=mode),
                patch.object(plugin, "collect_values", return_value={"prompt": "script"}),
                patch.object(plugin, "generate") as generate,
                patch("sg_plugins.panel.run_panel") as panel,
                patch("sg_plugins.generation_base.Gimp.progress_end"),
            ):
                procedure, image, config = MagicMock(), MagicMock(), MagicMock()
                plugin.main(procedure, mode, image, [], config, None)
                generate.assert_called_once_with(image, config, {"prompt": "script"})
                panel.assert_not_called()

    def test_startup_accepts_one_generate_then_runs_after_editor_restoration(self) -> None:
        session = PanelSession.__new__(PanelSession)
        session.closing = session.pending_generate = False
        session.editor = session.task = None
        session.image = None
        procedure, config, image = MagicMock(), MagicMock(), MagicMock()
        config.get_property.side_effect = {"action": "generate", "image": image, "mode": "current"}.__getitem__
        session.command(procedure, config, None)
        assert session.pending_generate
        assert session.image is image
        session.command(procedure, config, None)
        assert procedure.new_return_values.call_args.args[0] == Gimp.PDBStatusType.CANCEL

        restored = MagicMock(spec=GenerationDialog)

        def restore(_options, _catalog):
            session.editor = restored

        def generate():
            assert session.editor is restored
            assert not session.pending_generate
            return True

        future: Future[tuple] = Future()
        future.set_result(({}, MagicMock()))
        with (
            patch.object(session, "create_editor", side_effect=restore),
            patch.object(session, "generate", side_effect=generate) as run,
        ):
            session.connected(future)
        run.assert_called_once()

    def test_mode_menu_updates_target_and_mode_without_generating(self) -> None:
        session = PanelSession.__new__(PanelSession)
        session.closing = session.pending_generate = False
        session.task = None
        session.editor = MagicMock()
        session.window = MagicMock()
        procedure, config, image = MagicMock(), MagicMock(), MagicMock()
        config.get_property.side_effect = {"action": "present", "image": image, "mode": "inpaint"}.__getitem__
        with patch.object(session, "set_target") as target, patch.object(session, "generate") as generate:
            session.command(procedure, config, None)
        target.assert_called_once_with(image)
        session.editor.config.set_property.assert_called_once_with("generation_mode", "inpaint")
        session.window.present.assert_called_once()
        generate.assert_not_called()

    def test_generate_refreshes_canvas_before_collecting_current_parameters(self) -> None:
        session = PanelSession.__new__(PanelSession)
        session.closing = False
        session.task = None
        session.plugin = MagicMock(spec=GenerationPluginBase)
        session.plugin.settings = MagicMock()
        session.editor = editor = MagicMock()
        session.progress, session.status = MagicMock(), MagicMock()
        image, source, values = MagicMock(), MagicMock(), {"prompt": "edited", "seed": 77}

        def refresh():
            editor.image, editor.source = image, source

        editor.refresh_source.side_effect = refresh
        editor.collect_values.return_value = values
        with patch.object(session, "submit") as submit, patch("sg_plugins.panel.GLib.timeout_add_seconds"):
            assert session.generate()
        session.plugin.prepare_request.assert_called_once_with(image, editor.config, values, source)
        request = session.plugin.prepare_request.return_value
        submit.assert_called_once_with(request.run, session.generated, session.stop)

    def test_close_during_model_change_stops_generation_submission(self) -> None:
        request = self.request()
        stop = threading.Event()
        api = cast(MagicMock, request.api)
        api.post.side_effect = lambda *_args: stop.set()
        assert request.run(stop) is None
        api.post.assert_called_once_with("/sdapi/v1/options", {"sd_model_checkpoint": "model"})

    def test_result_uses_original_target_and_insertion_snapshot(self) -> None:
        request = self.request()
        response = {"images": ["image"], "info": json.dumps({"all_seeds": [123]})}
        with (
            patch("sg_plugins.generation_base.ResponseLayers") as layers,
            patch("sg_plugins.generation_base.Gimp.displays_flush"),
        ):
            assert request.insert(response) == 1
        layers.assert_called_once_with(request.image, response, {"skip_annotator_layers": True})
        layers.return_value.resize.assert_called_once_with(32, 32, strategy="Resize to selection")
        layers.return_value.resize.return_value.translate.assert_called_once_with((8, 16))
        request.image.undo_group_start.assert_called_once()
        request.image.undo_group_end.assert_called_once()

    def test_closed_target_and_failed_insertion_finish_at_the_result_boundary(self) -> None:
        request = self.request()
        request.image.is_valid.return_value = False
        with self.assertRaisesRegex(ValueError, "Target image closed"):  # noqa: PT027
            request.insert({})
        request.image.undo_group_start.assert_not_called()
        request.image.is_valid.return_value = True
        with (
            patch("sg_plugins.generation_base.ResponseLayers", side_effect=OSError("load failed")),
            self.assertRaisesRegex(OSError, "load failed"),  # noqa: PT027
        ):
            request.insert({})
        request.image.undo_group_end.assert_called_once()

    def test_worker_completion_is_delivered_on_the_main_thread(self) -> None:
        session = PanelSession.__new__(PanelSession)
        session.pending = set()
        session.closing = False
        owner = threading.get_ident()
        scheduled = threading.Event()
        worker_id: list[int] = []
        deliveries = []

        def received(future):
            assert threading.get_ident() == owner
            assert future.result()

        callback = MagicMock(side_effect=received)

        def work():
            worker_id.append(threading.get_ident())
            return True

        def idle(*args):
            deliveries.append(args)
            scheduled.set()

        with ThreadPoolExecutor(max_workers=1) as executor:
            session.executor = executor
            with patch("sg_plugins.panel.GLib.idle_add", side_effect=idle):
                session.submit(work, callback)
                assert scheduled.wait(2)
            callback.assert_not_called()
            deliver, future, receiver = deliveries[0]
            deliver(future, receiver)
        callback.assert_called_once()
        assert worker_id[0] != owner
        assert not session.pending

    def test_interrupted_results_are_inserted_without_completion_toast(self) -> None:
        session = PanelSession.__new__(PanelSession)
        task = self.request()
        session.task = task
        session.closing = True
        session.progress_timer = 0
        session.editor = MagicMock(spec=GenerationDialog)
        session.status = MagicMock()
        session.progress = MagicMock()
        future: Future[dict] = Future()
        response = {"images": ["finished"], "info": json.dumps({"all_seeds": [123]})}
        future.set_result(response)
        with (
            patch.object(GenerationRequest, "insert", return_value=1) as insert,
            patch.object(session, "submit") as submit,
        ):
            session.generated(future)
            submit.assert_not_called()
        insert.assert_called_once_with(response)
        assert session.task is None

    def test_close_interrupts_after_forge_starts_the_request(self) -> None:
        session = PanelSession.__new__(PanelSession)
        session.task = self.request()
        session.closing = True
        session.interrupt_sent = False
        session.progress = MagicMock()
        future: Future[tuple] = Future()
        future.set_result((session.task, {"progress": 0.2, "eta_relative": 5, "state": {"job_count": 1}}))
        with patch.object(session, "submit") as submit:
            session.progress_received(future)
            assert submit.call_args.args[2] == "/sdapi/v1/interrupt"
        assert session.interrupt_sent

    def test_successful_insertion_schedules_one_completion_notification(self) -> None:
        session = PanelSession.__new__(PanelSession)
        session.task = self.request()
        session.closing = False
        session.progress_timer = 0
        session.editor = MagicMock(spec=GenerationDialog)
        session.progress = MagicMock()
        session.status = MagicMock()
        session.notification = MagicMock()
        session.notification.get_active.return_value = True
        future: Future[dict] = Future()
        future.set_result({"images": ["finished"], "info": json.dumps({"all_seeds": [123]})})
        with patch.object(GenerationRequest, "insert", return_value=1), patch.object(session, "submit") as submit:
            session.generated(future)
        submit.assert_called_once()
        assert submit.call_args.args[3] == "original: 1 candidates"

    def test_notification_errors_keep_the_status_compact(self) -> None:
        session = PanelSession.__new__(PanelSession)
        session.status = MagicMock()
        future: Future[None] = Future()
        future.set_exception(subprocess.CalledProcessError(1, ["powershell", "-EncodedCommand", "x" * 5000]))
        session.notified(future)
        session.status.set_text.assert_called_once_with("Notification failed with exit code 1")

    def test_temporary_generate_command_reports_busy(self) -> None:
        session = PanelSession.__new__(PanelSession)
        session.closing = False
        session.pending_generate = False
        session.editor = MagicMock(spec=GenerationDialog)
        session.task = self.request()
        procedure, config = MagicMock(), MagicMock()
        config.get_property.side_effect = {"action": "generate", "image": None}.__getitem__
        session.command(procedure, config, None)
        assert procedure.new_return_values.call_args.args[0] == Gimp.PDBStatusType.CANCEL

    def test_panel_writes_keep_other_windows_settings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "settings.json")
            panel = MyShelf({"prompt": "old"}, file_path=path)
            panel.save()
            global_settings = MyShelf(file_path=path)
            global_settings.save({"prompt": "new"})
            state = {"parameters": {"seed": 123}, "file_path": "settings.txt", "width": 360, "height": 600}
            panel.save({"panel_state": state})
            restored = MyShelf(file_path=path)
            assert restored.get("prompt") == "new"
            assert restored.get("panel_state") == state
