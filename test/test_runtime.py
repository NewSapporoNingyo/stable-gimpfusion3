from __future__ import annotations

import base64
import json
import threading
import unittest

from concurrent.futures import wait
from pathlib import Path
from unittest.mock import MagicMock, patch

import gi
import requests

from sg_generation import insertion_size
from sg_loras import LoraCatalog
from sg_plugins.config import ConfigModelPlugin
from sg_plugins.generation_base import GenerationPluginBase
from sg_sources import GenerationSource
from sg_structures import ApiClient, Layer, ResponseLayers

gi.require_version("Gimp", "3.0")
from gi.repository import Gimp


class RuntimeTests(unittest.TestCase):
    def test_layer_import_releases_temporary_file_on_success_and_failure(self) -> None:
        paths: list[Path] = []
        drawable = MagicMock()

        def load_layer(_run_mode, _image, file):
            path = Path(file.get_path())
            paths.append(path)
            assert path.read_bytes() == b"image data"
            return drawable

        encoded = base64.b64encode(b"image data").decode()
        with patch("sg_structures.Gimp.file_load_layer", side_effect=load_layer):
            assert Layer.fromBase64(MagicMock(), encoded).layer is drawable
        assert not paths[0].parent.exists()

        def fail_load(*args):
            load_layer(*args)
            raise OSError("image load failed")

        with (
            patch("sg_structures.Gimp.file_load_layer", side_effect=fail_load),
            self.assertRaisesRegex(OSError, "image load failed"),  # noqa: PT027
        ):
            Layer.fromBase64(MagicMock(), encoded)
        assert not paths[1].parent.exists()
        assert paths[0].parent != paths[1].parent

    def test_aspect_preview_matches_imported_layer_dimensions(self) -> None:
        values = {"generation_mode": "txt2img", "width": 512, "height": 384}
        response = {"images": ["eA=="], "info": json.dumps({
            "width": 512, "height": 384, "all_seeds": [1], "infotexts": ["test"],
        })}
        for strategy in ("Resize to selection", "Aspect fill", "Aspect fit", "Insert as is"):
            values["insert_mode"] = strategy
            drawable = MagicMock()
            drawable.get_parasite.return_value = None
            with patch("sg_structures.Gimp.file_load_layer", return_value=drawable):
                layers = ResponseLayers(MagicMock(), response)
                layers.resize(383, 259, strategy)
            if strategy == "Insert as is":
                drawable.scale.assert_not_called()
            else:
                drawable.scale.assert_called_once_with(*insertion_size(values, (383, 259), (512, 384)), False)

    def test_api_timeout_override_and_http_errors(self) -> None:
        client = ApiClient("http://example.test", timeout=300)
        response = MagicMock()
        response.json.return_value = {"progress": 0.5}
        with patch("sg_structures.requests.get", return_value=response) as get:
            assert client.get("/progress", timeout=5) == {"progress": 0.5}
            assert get.call_args.kwargs["timeout"] == 5
            client.get("/options")
            assert get.call_args.kwargs["timeout"] == 300
            response.raise_for_status.side_effect = requests.HTTPError("failed response")
            with self.assertRaises(requests.HTTPError):  # noqa: PT027
                client.get("/options")
            response.raise_for_status.side_effect = None
            response.json.side_effect = requests.JSONDecodeError("invalid JSON", "{", 1)
            with self.assertRaises(requests.JSONDecodeError):  # noqa: PT027
                client.get("/options")

    def run_generation(self, *, progress_failure: bool, generation_failure: bool) -> None:
        api = MagicMock(spec=ApiClient)
        settings = MagicMock()
        settings.get.side_effect = {"prompt": "", "negative_prompt": "", "cache_tobase64": True}.get
        plugin = GenerationPluginBase(api, settings)
        values = {
            "generation_mode": "txt2img", "width": 64, "height": 64, "insert_mode": "Insert as is",
            "prompt": "test", "negative_prompt": "", "seed": 0, "batch_size": 1, "steps": 5,
            "cfg_scale": 5, "sampler_index": "Euler", "restore_faces": False, "tiling": False,
            "loras": [], "invert_mask": False, "cn1_enabled": False, "cn2_enabled": False,
            "cn_skip_annotator_layers": True, "sd_model_checkpoint": "model",
        }
        source = GenerationSource("test", (64, 64), (0, 0, 64, 64), None, "", (0, 0), None, None, "")
        released = threading.Event()
        main_thread = threading.current_thread()
        workers: list[threading.Thread] = []

        def post(endpoint, _data):
            if endpoint == "/sdapi/v1/options":
                return None
            workers.append(threading.current_thread())
            assert released.wait(2)
            if generation_failure:
                raise requests.ConnectionError("generation failed")
            return {"images": [], "info": json.dumps({"all_seeds": []})}

        def progress(*_args, **_kwargs):
            assert threading.current_thread() is main_thread
            released.set()
            if progress_failure:
                raise requests.Timeout("progress timed out")
            return {"progress": 0.5, "state": {"job_count": 1}, "eta_relative": 1}

        api.post.side_effect = post
        api.get.side_effect = progress
        with (
            patch("sg_plugins.generation_base.wait", side_effect=lambda fs, timeout: wait(fs, timeout=0.01)),
            patch("sg_plugins.generation_base.Gimp.progress_init"),
            patch("sg_plugins.generation_base.Gimp.progress_update") as update,
            patch("sg_plugins.generation_base.Gimp.progress_set_text"),
            patch("sg_plugins.generation_base.Gimp.message") as message,
            patch("sg_plugins.generation_base.Gimp.displays_flush"),
            patch("sg_plugins.generation_base.ResponseLayers") as layers,
        ):
            if generation_failure:
                with self.assertRaisesRegex(requests.ConnectionError, "generation failed"):  # noqa: PT027
                    plugin.generate(MagicMock(), MagicMock(), values, LoraCatalog([], "Filename"), source)
                layers.assert_not_called()
            else:
                plugin.generate(MagicMock(), MagicMock(), values, LoraCatalog([], "Filename"), source)
                layers.assert_called_once()
            assert message.call_count == int(progress_failure)
            assert update.call_count == int(not progress_failure)
        assert workers[0] is not main_thread
        assert not workers[0].is_alive()
        assert api.get.call_args.kwargs["timeout"] == 5

    def test_generation_finishes_while_server_progress_remains_busy(self) -> None:
        self.run_generation(progress_failure=False, generation_failure=False)

    def test_progress_network_error_keeps_generation_result(self) -> None:
        self.run_generation(progress_failure=True, generation_failure=False)

    def test_generation_error_propagates_and_closes_worker(self) -> None:
        self.run_generation(progress_failure=False, generation_failure=True)

    def test_model_change_ends_progress_after_request_error(self) -> None:
        api, settings, procedure, config = (MagicMock() for _index in range(4))
        config.get_property.side_effect = {
            "model": "test", "flux_encoders_mode": "Never add", "flux-encoders": "",
        }.get
        api.post.side_effect = requests.ConnectionError("offline")
        with (
            patch("sg_plugins.config.Gimp.progress_init"),
            patch("sg_plugins.config.Gimp.progress_set_text"),
            patch("sg_plugins.config.Gimp.progress_end") as end,
        ):
            ConfigModelPlugin(api, settings).main(procedure, Gimp.RunMode.NONINTERACTIVE, MagicMock(), [], config, None)
        assert procedure.new_return_values.call_args.args[0] == Gimp.PDBStatusType.CALLING_ERROR
        end.assert_called_once()
