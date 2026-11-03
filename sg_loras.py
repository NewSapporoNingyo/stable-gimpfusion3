"""LoRA selections and prompt composition using Forge's name and alias rules."""

from __future__ import annotations

import math
import re

from typing import Any, TypedDict, cast

from sg_i18n import _


class LoraSelection(TypedDict):
    name: str
    alias: str
    weight: float
    enabled: bool


class LoraModel(TypedDict):
    name: str
    alias: str
    path: str
    metadata: dict[str, Any]


def validate_loras(value: Any) -> list[LoraSelection]:
    error = _("Invalid preset field: {field}").format(field="loras")
    if not isinstance(value, list):
        raise ValueError(error)
    names = set()
    for item in value:
        if (
            not isinstance(item, dict) or not {"name", "alias", "weight", "enabled"} <= item.keys()
            or not isinstance(item["name"], str) or not item["name"]
            or not isinstance(item["alias"], str) or not item["alias"]
            or type(item["enabled"]) is not bool or type(item["weight"]) not in (int, float)
            or not math.isfinite(item["weight"]) or item["name"] in names
        ):
            raise ValueError(error)
        names.add(item["name"])
    return cast(list[LoraSelection], value)


def parse_weight(text: str) -> float:
    try:
        weight = float(text)
    except ValueError as error:
        raise ValueError(_("Enter a finite LoRA weight")) from error
    if not math.isfinite(weight):
        raise ValueError(_("Enter a finite LoRA weight"))
    return weight


class LoraCatalog:
    def __init__(self, models: list[LoraModel], preferred_name: str) -> None:
        self.models = models
        self.preferred_name = preferred_name
        self.by_name = {model["name"]: model for model in models}
        self.aliases: dict[str, str] = {}
        # Forge networks.process_network_files builds this lookup in API order.
        self.forbidden_aliases = {"none", "Addams"}
        for model in models:
            if model["alias"] in self.aliases:
                self.forbidden_aliases.add(model["alias"].lower())
            self.aliases[model["name"]] = model["name"]
            self.aliases[model["alias"]] = model["name"]

    def resolve(self, identifier: str) -> str | None:
        if identifier.lower() in self.forbidden_aliases:
            return identifier if identifier in self.by_name else None
        return self.aliases.get(identifier)

    def reference(self, item: LoraSelection) -> str:
        if self.preferred_name == "Filename" or item["alias"].lower() in self.forbidden_aliases:
            return item["name"]
        return item["alias"]


LORA_TAG = re.compile(r"<lora:([^>]+)>")


def compose_prompt(
    prompt: str, suffix: str, selections: list[LoraSelection], catalog: LoraCatalog,
) -> tuple[str, list[str]]:
    enabled = {item["name"]: item for item in selections if item["enabled"]}
    missing_identifiers = {
        identifier: item["name"]
        for item in enabled.values() if item["name"] not in catalog.by_name
        for identifier in (item["name"], item["alias"])
    }
    emitted: set[str] = set()

    def tag(item: LoraSelection) -> str:
        return f"<lora:{catalog.reference(item)}:{item['weight']}>"

    def replace(match: re.Match[str]) -> str:
        identifier = match.group(1).split(":", 1)[0]
        name = catalog.resolve(identifier)
        if name is None:
            name = missing_identifiers.get(identifier)
        if name not in enabled:
            return match.group(0)
        if name in emitted:
            return ""
        emitted.add(name)
        return tag(enabled[name])

    combined = LORA_TAG.sub(replace, f"{prompt} {suffix}".strip())
    added = [tag(item) for name, item in enabled.items() if name not in emitted]
    combined = " ".join([combined, *added]).strip()
    return combined, [match.group(0) for match in LORA_TAG.finditer(combined)]
