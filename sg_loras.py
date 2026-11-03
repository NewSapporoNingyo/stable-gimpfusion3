"""LoRA catalogue and Forge's extra-network prompt click behavior."""

from __future__ import annotations

import re

from typing import Any, TypedDict


class LoraModel(TypedDict):
    name: str
    alias: str
    path: str
    metadata: dict[str, Any]


# Forge javascript/extraNetworks.js uses this pattern for extra-network card clicks.
CLICK_TAG = re.compile(r"<([^:^>]+:[^:]+):[\d.]+>")


class LoraCatalog:
    def __init__(
        self, models: list[LoraModel], preferred_name: str, default_multiplier: float, separator: str,
    ) -> None:
        self.models = models
        self.preferred_name = preferred_name
        self.default_multiplier = default_multiplier
        self.separator = separator
        self.by_name = {model["name"]: model for model in models}
        aliases: set[str] = set()
        self.forbidden_aliases = {"none", "Addams"}
        for model in models:
            if model["alias"] in aliases:
                self.forbidden_aliases.add(model["alias"].lower())
            aliases.update((model["name"], model["alias"]))

    def reference(self, item: LoraModel) -> str:
        if self.preferred_name == "Filename" or item["alias"].lower() in self.forbidden_aliases:
            return item["name"]
        return item["alias"]

    def toggle_prompt(self, prompt: str, name: str) -> str:
        reference = "lora:" + self.reference(self.by_name[name])
        position = -1

        def remove(match: re.Match[str]) -> str:
            nonlocal position
            if match.group(1) == reference:
                position = match.start()
                return ""
            return match.group(0)

        result = CLICK_TAG.sub(remove, prompt)
        if position < 0:
            return prompt + self.separator + f"<{reference}:{self.default_multiplier:g}>"
        start = position - len(self.separator)
        if result[start:position] == self.separator:
            result = result[:start] + result[position:]
        return result
