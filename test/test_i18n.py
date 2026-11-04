from __future__ import annotations

import unittest

from pathlib import Path
from unittest.mock import patch

from sg_i18n import DOMAIN, setup_i18n


class TranslationTests(unittest.TestCase):
    def test_gimp_language_selection_loads_real_catalogs(self) -> None:
        for names, expected in (
            (["en_US", "en", "C"], "Generate"),
            (["it_IT", "it", "C"], "Genera"),
            (["ru_RU", "ru", "C"], "Создать"),
            (["zh_CN", "zh", "C"], "生成"),
            (["zhcn", "C"], "生成"),
            (["C"], "Generate"),
        ):
            with self.subTest(names=names), patch("sg_i18n.GLib.get_language_names", return_value=names):
                assert setup_i18n()("Generate") == expected

    def test_native_chinese_catalog_matches_python_catalog(self) -> None:
        directory = Path(__file__).resolve().parents[1] / "locale"
        assert (directory / "zh_CN/LC_MESSAGES" / f"{DOMAIN}.mo").read_bytes() == (
            directory / "zhcn/LC_MESSAGES" / f"{DOMAIN}.mo"
        ).read_bytes()
