from __future__ import annotations

import json
import tempfile
import unittest

from pathlib import Path

from sg_generation import build_request, generation_size, insertion_size, integer_seed
from sg_loras import LoraCatalog
from sg_structures import MyShelf


class PresetTests(unittest.TestCase):
    def test_legacy_settings_and_named_presets_survive_reload(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            path.write_text('{"api_base": "http://example.test", "prompt": "suffix"}', encoding="utf-8")
            shelf = MyShelf({"steps": 20}, file_path=str(path))
            assert shelf.get("presets") == {}
            preset = {"generation_mode": "txt2img", "seed": 0, "inpaint_full_res_padding": 32, "loras": [
                {"name": "model", "alias": "tag", "weight": 0.75, "enabled": True},
                {"name": "slider", "alias": "slider alias", "weight": -0.5, "enabled": False},
                {"name": "zero", "alias": "zero", "weight": 0, "enabled": True},
            ]}
            shelf.save_preset("预设一", preset)
            shelf.save_preset("预设二", {**preset, "seed": 4294967295})
            reloaded = MyShelf(file_path=str(path))
            assert reloaded.get("presets")["预设一"] == preset
            assert reloaded.get("presets")["预设二"]["loras"] == preset["loras"]
            assert reloaded.get("last_preset") == "预设二"
            assert reloaded.get("prompt") == "suffix"
            assert reloaded.get("api_base") == "http://example.test"
            assert reloaded.get("steps") == 20
            assert "预设一" in path.read_text(encoding="utf-8")
            reloaded.delete_preset("预设一")
            assert reloaded.get("last_preset") == "预设二"
            reloaded.delete_preset("预设二")
            assert MyShelf(file_path=str(path)).get("last_preset") is None

    def test_existing_presets_keep_their_inpaint_settings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            presets = {"existing": {"inpaint_full_res": True}, "new": {"inpaint_full_res_padding": 128}}
            path.write_text(json.dumps({"presets": presets}), encoding="utf-8")
            shelf = MyShelf(file_path=str(path))
            assert shelf.get("presets")["existing"] == {
                "inpaint_full_res": True, "inpaint_full_res_padding": 10,
            }
            assert shelf.get("presets")["new"]["inpaint_full_res_padding"] == 128
            shelf.save()
            assert MyShelf(file_path=str(path)).get("presets") == shelf.get("presets")

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
            "prompt": "local prompt", "negative_prompt": "local negative", "seed": 0,
            "batch_size": 2, "steps": 5, "cfg_scale": 5.0, "sampler_index": "Euler",
            "restore_faces": False, "tiling": False, "denoising_strength": 0.6,
            "resize_mode": "Just Resize", "mask_blur": 4, "inpainting_fill": "original",
            "inpaint_full_res": True, "inpaint_full_res_padding": 32, "invert_mask": True,
            "loras": [{"name": "slider", "alias": "slider", "weight": -0.5, "enabled": True}],
        }
        catalog = LoraCatalog([], "Alias from file")
        text = build_request(values, "global suffix", "global negative", (384, 256), catalog)
        assert text["prompt"] == "local prompt global suffix <lora:slider:-0.5>"
        assert text["negative_prompt"] == "local negative global negative"
        assert (text["width"], text["height"]) == (512, 512)
        assert text["seed"] == 0
        assert "denoising_strength" not in text
        assert insertion_size(values, (384, 256), (640, 512)) == (384, 256)
        for mode in ("txt2img", "img2img", "inpaint"):
            values.update(generation_mode=mode, width=1269, height=1660)
            with self.assertRaisesRegex(ValueError, "multiples of 8"):  # noqa: PT027
                build_request(values, "", "", (383, 259), catalog)
            values.update(width=1272, height=1664)
            corrected = build_request(values, "", "", (383, 259), catalog)
            assert (corrected["width"], corrected["height"]) == (1272, 1664)
            assert corrected["prompt"] == "local prompt <lora:slider:-0.5>"
        values.update(generation_mode="txt2img", width=513, height=516)
        values["insert_mode"] = "Use selection size"
        assert generation_size(values, (383, 259)) == (384, 256)
        selection = build_request(values, "", "", (383, 259), catalog)
        assert (selection["width"], selection["height"]) == (384, 256)
        for tiny_selection in ((1, 1), (4, 64), (64, 4)):
            with self.assertRaisesRegex(ValueError, "positive multiples of 8"):  # noqa: PT027
                build_request(values, "", "", tiny_selection, catalog)
        values.update(width=512, height=384)
        values["generation_mode"] = "img2img"
        image = build_request(values, "", "", (383, 259), catalog)
        assert (image["width"], image["height"]) == (512, 384)
        assert insertion_size(values, (383, 259), (640, 512)) == (512, 384)
        assert image["denoising_strength"] == 0.6
        values.update(width=512, height=512)
        values["generation_mode"] = "inpaint"
        inpaint = build_request(values, "", "", (384, 256), catalog)
        assert (inpaint["width"], inpaint["height"]) == (512, 512)
        assert inpaint["inpainting_fill"] == 1
        assert inpaint["inpainting_mask_invert"] == 1
        assert insertion_size(values, (384, 256), (768, 512)) == (768, 512)
        for padding in (0, 32, 128):
            values["inpaint_full_res_padding"] = padding
            assert build_request(values, "", "", (384, 256), catalog)["inpaint_full_res_padding"] == padding
        values["inpaint_full_res"] = False
        assert insertion_size(values, (384, 256), (768, 512)) == (512, 512)
        values["generation_mode"] = "txt2img"
        values["insert_mode"] = "Aspect fit"
        assert insertion_size(values, (384, 256), (640, 512)) == (256, 256)
