"""Pixel snapshots for generation inputs and selection masks."""

from __future__ import annotations

import base64
import hashlib

from dataclasses import dataclass
from typing import ClassVar

import gi

from sg_i18n import _

gi.require_version("Gimp", "3.0")
gi.require_version("Gegl", "0.4")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, Gegl, Gimp, GLib


@dataclass(frozen=True)
class PixelSnapshot:
    width: int
    height: int
    channels: int
    data: bytes

    cache: ClassVar[dict[tuple[int, int, int, bytes], str]] = {}

    @classmethod
    def read(cls, drawable: Gimp.Drawable, *, alpha: bool = True) -> PixelSnapshot:
        width, height = drawable.get_width(), drawable.get_height()
        channels = 4 if alpha else 3
        pixels = drawable.get_buffer().get(
            Gegl.Rectangle.new(0, 0, width, height), 1.0,
            "R'G'B'A u8" if alpha else "R'G'B' u8", Gegl.AbyssPolicy.NONE,
        )
        return cls(width, height, channels, pixels)

    @classmethod
    def read_mask(cls, drawable: Gimp.Drawable) -> PixelSnapshot:
        width, height = drawable.get_width(), drawable.get_height()
        coverage = drawable.get_buffer().get(
            Gegl.Rectangle.new(0, 0, width, height), 1.0, "Y u8", Gegl.AbyssPolicy.NONE,
        )
        pixels = bytearray(width * height * 3)
        for channel in range(3):
            pixels[channel::3] = coverage
        return cls(width, height, 3, bytes(pixels))

    def pixbuf(self) -> GdkPixbuf.Pixbuf:
        return GdkPixbuf.Pixbuf.new_from_bytes(
            GLib.Bytes.new(self.data), GdkPixbuf.Colorspace.RGB, self.channels == 4,
            8, self.width, self.height, self.width * self.channels,
        )

    def to_base64(self, *, cache_enabled: bool = True) -> str:
        if cache_enabled:
            key = (self.width, self.height, self.channels, hashlib.sha256(self.data).digest())
            if key in self.cache:
                return self.cache[key]
        _success, png = self.pixbuf().save_to_bufferv("png", [], [])
        result = base64.b64encode(png).decode()
        if cache_enabled:
            if len(self.cache) == 10:
                del self.cache[next(iter(self.cache))]
            self.cache[key] = result
        return result

    def crop(self, x: int, y: int, width: int, height: int) -> PixelSnapshot:
        format_name = "R'G'B'A u8" if self.channels == 4 else "R'G'B' u8"
        buffer = Gegl.Buffer.new(format_name, 0, 0, self.width, self.height)
        buffer.set(Gegl.Rectangle.new(0, 0, self.width, self.height), format_name, self.data)
        pixels = buffer.get(Gegl.Rectangle.new(x, y, width, height), 1.0, format_name, Gegl.AbyssPolicy.NONE)
        return PixelSnapshot(width, height, self.channels, pixels)


@dataclass(frozen=True)
class GenerationSource:
    image_name: str
    image_size: tuple[int, int]
    selection_bounds: tuple[int, int, int, int]
    selection: PixelSnapshot | None
    layer_name: str
    offset: tuple[int, int]
    pixels: PixelSnapshot | None
    mask: PixelSnapshot | None
    mask_source: str

    @classmethod
    def capture(cls, image: Gimp.Image, mode: str) -> GenerationSource:
        Gegl.init(None)
        if not image.is_valid():
            raise ValueError(_("Open the target image"))
        _success, selected, x1, y1, x2, y2 = Gimp.Selection.bounds(image)
        selection = PixelSnapshot.read_mask(image.get_selection()) if selected else None
        layer_name, offset, mask_source = "", (0, 0), ""
        pixels: PixelSnapshot | None = None
        mask: PixelSnapshot | None = None
        if mode != "txt2img":
            layers = image.get_selected_layers()
            if layers:
                layer = layers[0]
                layer_name = layer.get_name()
                _success, x, y = layer.get_offsets()
                offset = x, y
                pixels = PixelSnapshot.read(layer)
                if mode == "inpaint":
                    if selection is not None:
                        mask = selection.crop(x, y, pixels.width, pixels.height)
                        mask_source = "selection"
                    elif layer.get_mask() is not None:
                        mask = PixelSnapshot.read_mask(layer.get_mask())
                        mask_source = "layer"
        return cls(
            image.get_name(), (image.get_width(), image.get_height()), (x1, y1, x2, y2), selection,
            layer_name, offset, pixels, mask, mask_source,
        )

    def problem(self, mode: str, invert_mask: bool) -> str:
        if mode == "txt2img":
            return ""
        if self.pixels is None:
            return _("Select a source layer")
        if mode == "inpaint":
            if self.mask is None:
                return _("Create a selection or add a source layer mask")
            active = any(value < 255 for value in self.mask.data) if invert_mask else any(self.mask.data)
            if not active:
                return _("Provide a mask with an area to inpaint within the source layer")
        return ""
