from __future__ import annotations

import json
import tempfile
import unittest

from pathlib import Path
from unittest.mock import MagicMock, patch

from sg_generation import (
    GENERATION_PARASITE,
    build_request,
    generation_size,
    insertion_size,
    integer_seed,
    parse_generation,
    serialize_generation,
)
from sg_plugins.generation_base import GenerationDialog, GenerationPluginBase
from sg_structures import MyShelf


def generation_values():
    values = {
        "generation_mode": "inpaint", "sd_model_checkpoint": "model", "prompt": "scene", "negative_prompt": "",
        "seed": -1, "batch_size": 1, "steps": 5, "cfg_scale": 5.0, "width": 512, "height": 384,
        "sampler_index": "Euler", "restore_faces": False, "tiling": False, "denoising_strength": 0.6,
        "resize_mode": "Just Resize", "mask_blur": 4, "inpainting_fill": "original", "inpaint_full_res": True,
        "inpaint_full_res_padding": 32, "invert_mask": False, "insert_mode": "Insert as is",
        "cn1_enabled": False, "cn2_enabled": False, "cn_skip_annotator_layers": True,
    }
    for slot in (1, 2):
        values.update({f"cn{slot}_{name}": value for name, value in {
            "module": "none", "model": "None", "weight": 1.0, "resize_mode": "Just Resize",
            "control_mode": "Balanced", "guidance_start": 0.0, "guidance_end": 1.0,
            "processor_res": 512, "threshold_a": 64.0, "threshold_b": 64.0,
        }.items()})
    return values


class GenerationSettingsTests(unittest.TestCase):
    def editor(self, values):
        editor = GenerationDialog.__new__(GenerationDialog)
        editor.plugin = GenerationPluginBase(MagicMock(), MagicMock())
        editor.procedure = MagicMock()
        editor.config = MagicMock()
        editor.config.get_property.side_effect = values.__getitem__
        editor.config.set_property.side_effect = values.__setitem__
        reader = patch.object(
            editor.plugin, "read_parameters", side_effect=lambda _procedure, text: parse_generation(text, values),
        )
        reader.start()
        self.addCleanup(reader.stop)
        editor.image = None
        editor.file_path = ""
        editor.settings_image = ""
        editor.pending_parameters = {}
        editor.error_label = MagicMock()
        editor.source_label = MagicMock()
        editor.source_preview = MagicMock()
        for name in ("refresh_mode", "refresh_settings_label"):
            handler = patch.object(editor, name)
            handler.start()
            self.addCleanup(handler.stop)
        return editor

    def test_ini_preserves_prompt_text_and_parameter_types(self) -> None:
        values = generation_values()
        values["prompt"] = '  中文 100% <lora:alias:-0.5>\n# text\n; text\n[section]\n\n  last = "value"  '
        values["negative_prompt"] = "line 1\r\n\tline 2\n"
        text = serialize_generation(values)
        assert text.startswith("[generation]\n")
        assert "中文" in text
        for seed in (-1, 0, 4294967295):
            values["seed"] = seed
            assert parse_generation(serialize_generation(values), generation_values()) == values

    def test_file_save_overwrite_save_as_and_load(self) -> None:
        values = generation_values()
        editor = self.editor(values)
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "配置一.txt"
            second = Path(directory) / "配置二.txt"
            with patch.object(editor, "choose_file", return_value=str(first.with_suffix(""))):
                editor.save_current()
            assert editor.file_path == str(first)
            values["prompt"] = "edited <lora:test:0.25>"
            editor.save_current()
            assert parse_generation(first.read_text(encoding="utf-8"), values)["prompt"] == values["prompt"]
            values["seed"] = 123
            with patch.object(editor, "choose_file", return_value=str(second)):
                editor.save_as()
            assert editor.file_path == str(second)
            assert parse_generation(first.read_text(encoding="utf-8"), values)["seed"] == -1
            values["prompt"] = "discarded"
            with patch.object(editor, "choose_file", return_value=str(first)):
                editor.load_file()
            assert values["prompt"] == "edited <lora:test:0.25>"
            assert editor.file_path == str(first)

    def test_mode_load_defers_fields_and_keeps_them_when_saving(self) -> None:
        saved = generation_values()
        current = {**saved, "generation_mode": "txt2img", "denoising_strength": 0.9, "inpainting_fill": "fill"}
        editor = self.editor(current)
        editor.load_parameters(saved)
        assert current["generation_mode"] == "txt2img"
        assert current["denoising_strength"] == 0.9
        assert editor.collect_values()["denoising_strength"] == 0.6
        current["generation_mode"] = "img2img"
        editor.refresh_source()
        assert current["denoising_strength"] == 0.6
        assert current["inpainting_fill"] == "fill"
        current["denoising_strength"] = 0.35
        current["generation_mode"] = "inpaint"
        editor.refresh_source()
        assert current["inpainting_fill"] == "original"
        assert editor.collect_values()["denoising_strength"] == 0.35
        assert editor.pending_parameters == {}

    def test_image_settings_are_written_and_loaded_manually(self) -> None:
        values = generation_values()
        editor = self.editor(values)
        editor.image = MagicMock()
        editor.image.get_name.return_value = "saved.xcf"
        editor.file_path = "previous.txt"
        with patch("sg_plugins.generation_base.Gimp.displays_flush"):
            editor.save_to_image()
        parasite = editor.image.attach_parasite.call_args.args[0]
        assert parasite.get_name() == GENERATION_PARASITE
        assert parasite.is_persistent()
        assert parasite.is_undoable()
        editor.image.get_parasite.return_value = parasite
        values["prompt"] = "edited"
        with patch.object(editor, "refresh_source"):
            editor.load_from_image()
        assert values["prompt"] == "scene"
        assert editor.file_path == ""
        assert editor.settings_image == "saved.xcf"

    def test_file_errors_keep_the_current_configuration(self) -> None:
        values = generation_values()
        editor = self.editor(values)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.txt"
            path.write_text("broken", encoding="utf-8")
            with patch.object(editor, "choose_file", return_value=str(path)):
                editor.load_file()
            assert values == generation_values()
            assert editor.file_path == ""
            assert editor.error_label.set_text.call_args.args[0]

    def test_storage_errors_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text("{", encoding="utf-8")
            with self.assertRaises(json.JSONDecodeError):  # noqa: PT027
                MyShelf(file_path=str(path))
            shelf = MyShelf(file_path=str(Path(directory) / "missing" / "settings.json"))
            with self.assertRaises(FileNotFoundError):  # noqa: PT027
                shelf.save()

    def test_seed_values_are_preserved(self) -> None:
        for value in (-1, 0, 70000, 4294967295):
            assert integer_seed(float(value)) == value
        for invalid_seed in (-2, 0.5, 4294967296):
            with self.assertRaises(ValueError):  # noqa: PT027
                integer_seed(invalid_seed)

    def test_mode_sizes_and_prompts_match_requests(self) -> None:
        values = {
            "generation_mode": "txt2img", "width": 512, "height": 512, "insert_mode": "Resize to selection",
            "prompt": "local prompt <lora:slider:-0.5>", "negative_prompt": "local negative", "seed": 0,
            "batch_size": 2, "steps": 5, "cfg_scale": 5.0, "sampler_index": "Euler",
            "restore_faces": False, "tiling": False, "denoising_strength": 0.6,
            "resize_mode": "Just Resize", "mask_blur": 4, "inpainting_fill": "original",
            "inpaint_full_res": True, "inpaint_full_res_padding": 32, "invert_mask": True,
        }
        text = build_request(values, "global suffix", "global negative", (384, 256))
        assert text["prompt"] == "local prompt <lora:slider:-0.5> global suffix"
        assert text["negative_prompt"] == "local negative global negative"
        assert (text["width"], text["height"]) == (512, 512)
        assert text["seed"] == 0
        assert "denoising_strength" not in text
        assert insertion_size(values, (384, 256), (640, 512)) == (384, 256)
        for mode in ("txt2img", "img2img", "inpaint"):
            values.update(generation_mode=mode, width=1269, height=1660)
            with self.assertRaisesRegex(ValueError, "multiples of 8"):  # noqa: PT027
                build_request(values, "", "", (383, 259))
            values.update(width=1272, height=1664)
            corrected = build_request(values, "", "", (383, 259))
            assert (corrected["width"], corrected["height"]) == (1272, 1664)
            assert corrected["prompt"] == "local prompt <lora:slider:-0.5>"
        values.update(generation_mode="txt2img", width=513, height=516)
        values["insert_mode"] = "Use selection size"
        assert generation_size(values, (383, 259)) == (384, 256)
        selection = build_request(values, "", "", (383, 259))
        assert (selection["width"], selection["height"]) == (384, 256)
        for tiny_selection in ((1, 1), (4, 64), (64, 4)):
            with self.assertRaisesRegex(ValueError, "positive multiples of 8"):  # noqa: PT027
                build_request(values, "", "", tiny_selection)
        values.update(width=512, height=384)
        values["generation_mode"] = "img2img"
        image = build_request(values, "", "", (383, 259))
        assert (image["width"], image["height"]) == (512, 384)
        assert insertion_size(values, (383, 259), (640, 512)) == (512, 384)
        assert image["denoising_strength"] == 0.6
        values.update(width=512, height=512)
        values["generation_mode"] = "inpaint"
        inpaint = build_request(values, "", "", (384, 256))
        assert (inpaint["width"], inpaint["height"]) == (512, 512)
        assert inpaint["inpainting_fill"] == 1
        assert inpaint["inpainting_mask_invert"] == 1
        assert insertion_size(values, (384, 256), (768, 512)) == (768, 512)
        for padding in (0, 32, 128):
            values["inpaint_full_res_padding"] = padding
            assert build_request(values, "", "", (384, 256))["inpaint_full_res_padding"] == padding
        values["inpaint_full_res"] = False
        assert insertion_size(values, (384, 256), (768, 512)) == (512, 512)
        values["generation_mode"] = "txt2img"
        values["insert_mode"] = "Aspect fit"
        assert insertion_size(values, (384, 256), (640, 512)) == (256, 256)
