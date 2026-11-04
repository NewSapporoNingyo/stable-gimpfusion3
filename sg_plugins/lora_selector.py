"""Shared GTK LoRA catalogue that edits the positive prompt."""

from __future__ import annotations

import json

from typing import Any

import gi

from sg_i18n import _
from sg_loras import LoraCatalog

gi.require_version("Gimp", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gimp, Gtk, Pango


class LoraSelector(Gtk.Box):
    def __init__(self, config: Gimp.ProcedureConfig, catalog: LoraCatalog) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.config = config
        self.catalog = catalog
        self.search = Gtk.SearchEntry(placeholder_text=_("Search LoRA name or alias"))
        self.pack_start(self.search, False, False, 0)
        self.refresh_button = Gtk.Button(label=_("Refresh LoRAs"))
        self.pack_start(self.refresh_button, False, False, 0)
        self.error_label = Gtk.Label(xalign=0, wrap=True)
        self.pack_start(self.error_label, False, False, 0)
        self.model = Gtk.ListStore(str, str)
        self.candidates = Gtk.TreeView(model=self.model, headers_visible=True, activate_on_single_click=True)
        for column, title in enumerate((_("LoRA name"), _("Alias"))):
            renderer = Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END)
            view_column = Gtk.TreeViewColumn(title, renderer, text=column)
            view_column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
            view_column.set_fixed_width(110)
            view_column.set_expand(True)
            self.candidates.append_column(view_column)
        candidate_scroll = Gtk.ScrolledWindow(height_request=110)
        candidate_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        candidate_scroll.add(self.candidates)
        self.pack_start(candidate_scroll, False, False, 0)
        self.details = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        detail_scroll = Gtk.ScrolledWindow(height_request=140)
        detail_scroll.add(self.details)
        detail_expander = Gtk.Expander(label=_("LoRA details"))
        detail_expander.add(detail_scroll)
        self.pack_start(detail_expander, False, False, 0)
        self.search.connect("search-changed", self.filter_catalog)
        self.candidates.get_selection().connect("changed", self.show_details)
        self.candidates.connect("row-activated", self.toggle_selected)
        self.filter_catalog()

    def filter_catalog(self, *_args: Any) -> None:
        query = self.search.get_text().casefold()
        self.model.clear()
        for item in self.catalog.models:
            if query in item["name"].casefold() or query in item["alias"].casefold():
                self.model.append((item["name"], item["alias"]))
        self.candidates.get_selection().select_path(Gtk.TreePath.new_first())

    def show_details(self, selection: Gtk.TreeSelection) -> None:
        model, iterator = selection.get_selected()
        if iterator is None:
            self.details.get_buffer().set_text("")
            return
        item = self.catalog.by_name[model[iterator][0]]
        self.details.get_buffer().set_text(
            item["path"] + "\n\n" + json.dumps(item["metadata"], ensure_ascii=False, indent=2),
        )

    def toggle_selected(self, _view: Gtk.TreeView, path: Gtk.TreePath, _column: Gtk.TreeViewColumn) -> None:
        prompt = self.config.get_property("prompt")
        self.config.set_property("prompt", self.catalog.toggle_prompt(prompt, self.model[path][0]))
