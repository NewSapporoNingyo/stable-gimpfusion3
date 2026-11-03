from __future__ import annotations

import unittest

from sg_loras import LoraCatalog, LoraModel


class LoraTests(unittest.TestCase):
    def setUp(self) -> None:
        self.models: list[LoraModel] = [
            {"name": "file", "alias": "training_alias", "path": "file.safetensors", "metadata": {}},
            {"name": "slider", "alias": "slider", "path": "slider.safetensors", "metadata": {}},
        ]
        self.catalog = LoraCatalog(self.models, "Alias from file", 1, " ")

    def test_click_adds_tag_and_removes_edited_weight(self) -> None:
        assert self.catalog.toggle_prompt("scene", "file") == "scene <lora:training_alias:1>"
        assert self.catalog.toggle_prompt("scene <lora:training_alias:0.25>", "file") == "scene"
        assert self.catalog.toggle_prompt("", "file") == " <lora:training_alias:1>"

    def test_click_uses_forge_multiplier_and_separator(self) -> None:
        catalog = LoraCatalog(self.models, "Filename", 0.75, ", ")
        assert catalog.toggle_prompt("scene", "file") == "scene, <lora:file:0.75>"
        assert catalog.toggle_prompt("scene, <lora:file:0.25>", "file") == "scene"

    def test_click_matches_forge_extra_network_pattern(self) -> None:
        prompt = "<lora:training_alias:0.2> <lora:slider:-0.5> <lora:training_alias:0.7:0.4:dyn=8>"
        assert self.catalog.toggle_prompt(prompt, "file") == (
            " <lora:slider:-0.5> <lora:training_alias:0.7:0.4:dyn=8>"
        )

    def test_filename_preference_and_conflicting_aliases(self) -> None:
        filename_catalog = LoraCatalog(self.models, "Filename", 1, " ")
        assert filename_catalog.reference(self.models[0]) == "file"
        models: list[LoraModel] = [
            *self.models, {"name": "other", "alias": "training_alias", "path": "other", "metadata": {}},
        ]
        conflicting = LoraCatalog(models, "Alias from file", 1, " ")
        assert conflicting.reference(models[0]) == "file"
