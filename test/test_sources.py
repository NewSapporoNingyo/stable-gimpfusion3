from __future__ import annotations

import unittest

from sg_sources import PixelSnapshot


class PixelSnapshotTests(unittest.TestCase):
    def test_encoding_tracks_pixel_edits_and_cache_switch(self) -> None:
        PixelSnapshot.cache.clear()
        original = PixelSnapshot(2, 2, 4, bytes([255, 0, 0, 255] * 4))
        edited = PixelSnapshot(2, 2, 4, bytes([0, 0, 255, 255] * 4))
        first = original.to_base64()
        assert original.to_base64() == first
        assert edited.to_base64() != first
        assert len(PixelSnapshot.cache) == 2
        PixelSnapshot.cache.clear()
        assert original.to_base64(cache_enabled=False) == first
        assert PixelSnapshot.cache == {}

    def test_mask_crop_uses_offsets_and_black_outside_canvas(self) -> None:
        from gi.repository import Gegl

        Gegl.init(None)
        selection = PixelSnapshot(3, 2, 3, bytes([0, 0, 0, 255, 255, 255, 0, 0, 0] * 2))
        assert selection.crop(1, 0, 2, 2).data == bytes([255, 255, 255, 0, 0, 0] * 2)
        negative = selection.crop(-1, -1, 3, 3)
        assert negative.data == bytes([0] * 9 + [0] * 6 + [255] * 3 + [0] * 6 + [255] * 3)
