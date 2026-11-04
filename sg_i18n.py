"""
Internationalization (i18n) support module for stable-gimpfusion3

GIMP automatically looks for .mo files in locale/ subdirectory
with text domain equal to the plug-in name.
"""

from __future__ import annotations

import gettext
import locale
import os

from collections.abc import Callable

from gi.repository import GLib

DOMAIN = "stable-gimpfusion3"


def setup_i18n() -> Callable[[str], str]:
    """Initialize internationalization support"""

    plugin_dir = os.path.dirname(os.path.abspath(__file__))
    locale_dir = os.path.join(plugin_dir, "locale")
    locale.setlocale(locale.LC_ALL, "")
    catalogs = {"en": "en", "it": "it", "ru": "ru", "zh_CN": "zhcn", "zhcn": "zhcn"}
    language = next((catalogs[name] for name in GLib.get_language_names() if name in catalogs), "en")
    translation = gettext.translation(DOMAIN, locale_dir, languages=[language])
    return translation.gettext


_: Callable[[str], str] = setup_i18n()
