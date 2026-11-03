from __future__ import annotations

import json
import unittest

from typing import Any

from sg_loras import LoraCatalog, LoraModel, LoraSelection, compose_prompt, parse_weight, validate_loras


class LoraTests(unittest.TestCase):
    def setUp(self) -> None:
        self.models: list[LoraModel] = [
            {"name": "file", "alias": "training_alias", "path": "file.safetensors", "metadata": {}},
            {"name": "slider", "alias": "slider", "path": "slider.safetensors", "metadata": {}},
        ]
        self.catalog = LoraCatalog(self.models, "Alias from file")

    def test_selector_replaces_alias_and_filename_at_first_position(self) -> None:
        prompt = "scene <lora:file:0.1> middle <lora:training_alias:0.2>"
        suffix = "suffix <lora:file:0.3>"
        selections: list[LoraSelection] = [
            {"name": "file", "alias": "training_alias", "weight": -0.75, "enabled": True},
            {"name": "slider", "alias": "slider", "weight": 0.0, "enabled": True},
        ]
        before = json.dumps(selections)
        expected = "scene <lora:training_alias:-0.75> middle  suffix  <lora:slider:0.0>"
        for _iteration in range(2):
            final, tags = compose_prompt(prompt, suffix, selections, self.catalog)
            assert final == expected
            assert tags == ["<lora:training_alias:-0.75>", "<lora:slider:0.0>"]
        assert json.dumps(selections) == before
        assert prompt == "scene <lora:file:0.1> middle <lora:training_alias:0.2>"
        assert suffix == "suffix <lora:file:0.3>"

    def test_handwritten_tags_keep_forge_order_and_arguments(self) -> None:
        prompt = "scene <lora:file:0.1> <lora:training_alias:0.7:0.4:dyn=8> <hypernet:other:1>"
        suffix = "<lora:slider:0.5> <lora:slider:0.5>"
        selections: list[LoraSelection] = [
            {"name": "file", "alias": "training_alias", "weight": 2.0, "enabled": False},
        ]
        final, tags = compose_prompt(prompt, suffix, selections, self.catalog)
        assert final == prompt + " " + suffix
        assert len(tags) == 4

    def test_missing_selections_keep_saved_identifiers(self) -> None:
        selections: list[LoraSelection] = [
            {"name": "missing_file", "alias": "missing_alias", "weight": 0.25, "enabled": True},
        ]
        final, tags = compose_prompt("<lora:missing_file:1> <lora:missing_alias:2>", "", selections, self.catalog)
        assert final == "<lora:missing_alias:0.25>"
        assert tags == [final]
        assert compose_prompt("<lora:unknown:1>", "", [], self.catalog)[0] == "<lora:unknown:1>"

    def test_forge_filename_preference_and_conflicting_aliases(self) -> None:
        selections: list[LoraSelection] = [
            {"name": "file", "alias": "training_alias", "weight": 1.0, "enabled": True},
        ]
        filename_catalog = LoraCatalog(self.models, "Filename")
        assert compose_prompt("", "", selections, filename_catalog)[0] == "<lora:file:1.0>"
        models: list[LoraModel] = [
            *self.models, {"name": "other", "alias": "training_alias", "path": "other", "metadata": {}},
        ]
        conflicting = LoraCatalog(models, "Alias from file")
        assert conflicting.resolve("training_alias") is None
        assert conflicting.resolve("file") == "file"
        assert conflicting.resolve("FILE") is None
        final, _tags = compose_prompt("<lora:file:0.1>", "", selections, conflicting)
        assert final == "<lora:file:1.0>"

    def test_weight_and_json_input_contract(self) -> None:
        for text, expected in (("-12.125", -12.125), ("0", 0), ("1e-8", 1e-8)):
            assert parse_weight(text) == expected
        for text in ("", "abc", "nan", "inf"):
            with self.assertRaises(ValueError):  # noqa: PT027
                parse_weight(text)
        valid = [{"name": "file", "alias": "tag", "weight": -12.125, "enabled": True}]
        assert validate_loras(valid) is valid
        invalid_values: tuple[Any, ...] = (
            {}, [{}], [{**valid[0], "weight": True}], [{**valid[0], "weight": float("nan")}], valid * 2,
        )
        for value in invalid_values:
            with self.assertRaises(ValueError):  # noqa: PT027
                validate_loras(value)
