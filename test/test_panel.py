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

from sg_plugins.generation_base import GenerationDialog, GenerationRequest
from sg_plugins.panel import PanelSession
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
        session.editor = MagicMock(spec=GenerationDialog)
        session.task = self.request()
        procedure, config = MagicMock(), MagicMock()
        config.get_property.side_effect = {"action": "generate", "image": None}.__getitem__
        session.command(procedure, config, None)
        assert procedure.new_return_values.call_args.args[0] == Gimp.PDBStatusType.CANCEL

    def test_panel_and_preset_writes_keep_other_windows_settings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "settings.json")
            panel = MyShelf({"prompt": "old"}, file_path=path)
            panel.save()
            global_settings = MyShelf(file_path=path)
            global_settings.save({"prompt": "new"})
            panel.save_preset("saved", {"generation_mode": "txt2img", "inpaint_full_res_padding": 32})
            state = {"parameters": {"seed": 123, "loras": []}, "width": 360, "height": 600}
            panel.save({"panel_state": state})
            restored = MyShelf(file_path=path)
            assert restored.get("prompt") == "new"
            assert restored.get("panel_state") == state
            assert "saved" in restored.get("presets")
