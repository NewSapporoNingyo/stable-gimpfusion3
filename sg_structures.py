from __future__ import annotations

import base64
import json
import logging
import os
import tempfile

from typing import Any

import gi
import requests

from sg_constants import INSERT_MODES
from sg_generation import aspect_resize
from sg_i18n import _
from sg_sources import PixelSnapshot

gi.require_version("Gimp", "3.0")
gi.require_version("Gegl", "0.4")
from gi.repository import Gegl, Gimp, Gio


class LayerData:
    def __init__(self, layer: Gimp.Layer) -> None:
        self.name = "gimpfusion"
        self.layer = layer
        self.load()

    def load(self) -> dict[str, Any]:
        parasite = self.layer.get_parasite(self.name)
        self.data: dict[str, Any] = {} if parasite is None else json.loads(bytes(parasite.get_data()))
        return self.data

    def save(self, data: dict[str, Any]) -> None:
        data_as_str = json.dumps(data)
        parasite = Gimp.Parasite.new(self.name, Gimp.PARASITE_PERSISTENT, data_as_str.encode())
        self.layer.attach_parasite(parasite)


layer_counter = 1


class Layer:
    def __init__(self, layer: Gimp.Layer) -> None:
        global layer_counter
        self.id = layer_counter
        layer_counter += 1
        self.layer = layer

    @staticmethod
    def fromBase64(img: Gimp.Image, base64Data: str) -> Layer:
        with tempfile.TemporaryDirectory(prefix="gimpfusion-") as directory:
            filepath = os.path.join(directory, "generated.png")
            with open(filepath, "wb") as image_file:
                image_file.write(base64.b64decode(base64Data))
            layer = Gimp.file_load_layer(Gimp.RunMode.NONINTERACTIVE, img, Gio.File.new_for_path(filepath))
            return Layer(layer)

    def rename(self, name):
        self.layer.set_name(name)
        return self

    def saveData(self, data):
        LayerData(self.layer).save(data)
        return self

    def resize(self, width, height):
        logging.info("Resizing to %dx%d", width, height)
        self.layer.scale(width, height, False)

    def translate(self, offset=None):
        if offset is not None:
            self.layer.set_offsets(offset[0], offset[1])
        return self

    def insertTo(self, image: Gimp.Image) -> Layer:
        image.insert_layer(self.layer, None, -1)
        return self


class ResponseLayers:
    def __init__(self, img: Gimp.Image, response: dict[str, Any], options: dict[str, Any] | None = None) -> None:
        if options is None:
            options = {"skip_annotator_layers": True}
        info = json.loads(response["info"])
        infotexts = info["infotexts"]
        seeds = info["all_seeds"]
        self.generated_width = info["width"]
        self.generated_height = info["height"]
        self.layers: list[Gimp.Layer] = []
        for index, image in enumerate(response["images"]):
            if index >= len(seeds) and options["skip_annotator_layers"]:
                continue
            layer = Layer.fromBase64(img, image)
            if index < len(seeds):
                layer.rename(_("Generated Layer {seed}").format(seed=seeds[index])).saveData({
                    "info": infotexts[index], "seed": seeds[index],
                })
            else:
                layer.rename(_("ControlNet auxiliary layer"))
            layer.insertTo(img)
            self.layers.append(layer.layer)

    def resize(self, width: int, height: int, strategy: str = INSERT_MODES[0]) -> ResponseLayers:
        if strategy == "Resize to selection":
            size = width, height
        elif strategy in ("Aspect fill", "Aspect fit"):
            size = aspect_resize(
                (width, height), (self.generated_width, self.generated_height),
                fill=strategy == "Aspect fill",
            )
        else:
            return self
        for layer in self.layers:
            Layer(layer).resize(*size)
        return self

    def translate(self, offset: tuple[int, int] | None = None) -> ResponseLayers:
        if offset is not None:
            for layer in self.layers:
                Layer(layer).translate(offset)
        return self

    def addSelectionAsMask(self, selection: PixelSnapshot | None) -> ResponseLayers:
        if selection is not None:
            source = Gegl.Buffer.new("Y u8", 0, 0, selection.width, selection.height)
            source.set(Gegl.Rectangle.new(0, 0, selection.width, selection.height), "Y u8", selection.data[::3])
            for layer in self.layers:
                _success, x, y = layer.get_offsets()
                width, height = layer.get_width(), layer.get_height()
                mask = layer.create_mask(Gimp.AddMaskType.WHITE)
                buffer = mask.get_buffer()
                source.copy(
                    Gegl.Rectangle.new(x, y, width, height), Gegl.AbyssPolicy.NONE,
                    buffer, Gegl.Rectangle.new(0, 0, width, height),
                )
                buffer.flush()
                layer.add_mask(mask)
        return self


class MyShelf:
    """GimpShelf is not available at init time, so we keep our persistent data in a json file"""

    def __init__(self, default_shelf: dict[str, Any] | None = None, *, file_path: str | None = None) -> None:
        if default_shelf is None:
            default_shelf = {}
        self.file_path = file_path or os.path.join(
            os.path.dirname(os.path.realpath(__file__)), "stable_gimpfusion.json",
        )
        self.load(default_shelf)

    def load(self, default_shelf: dict[str, Any]) -> None:
        self.data = {**default_shelf}
        self.reload()

    def reload(self) -> None:
        if os.path.isfile(self.file_path):
            with open(self.file_path, encoding="utf-8") as file:
                self.data.update(json.load(file))

    def save(self, data: dict[str, Any] | None = None) -> None:
        if data is not None:
            self.reload()
            self.data.update(data)
        with open(self.file_path, "w", encoding="utf-8") as file:
            json.dump(self.data, file, ensure_ascii=False, indent=2)

    def get(self, name, default_value=None):
        return self.data.get(name, default_value)

    def set(self, name, default_value=None):
        self.save({name: default_value})


class ApiClient:
    """Simple API client used to interface with StableDiffusion JSON endpoints"""

    def __init__(self, base_url: str, timeout: float = 300) -> None:
        self.base_url = base_url.strip("/")
        self.timeout = timeout

    def post(
        self, endpoint: str, data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None, headers: dict[str, str] | None = None,
    ) -> Any:
        url = self.base_url + endpoint
        headers = headers or {"Content-Type": "application/json", "Accept": "application/json"}
        logging.debug(f"POST {url}, data {data.keys() if data else None}")
        response = requests.post(url=url, params=params, headers=headers, json=data, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def get(
        self, endpoint: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None,
        *, timeout: float | None = None,
    ) -> Any:
        url = self.base_url + endpoint
        headers = headers or {"Content-Type": "application/json", "Accept": "application/json"}
        logging.debug(f"GET {url}")
        response = requests.get(
            url=url, params=params, headers=headers, timeout=self.timeout if timeout is None else timeout,
        )
        response.raise_for_status()
        return response.json()
