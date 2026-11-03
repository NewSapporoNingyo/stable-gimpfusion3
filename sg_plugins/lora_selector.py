"""Shared GTK LoRA selector bound to the generation configuration."""

from __future__ import annotations

import json

from collections.abc import Callable
from typing import Any

import gi
import requests

from sg_i18n import _
from sg_loras import LoraCatalog, LoraSelection, compose_prompt, parse_weight
from sg_structures import ApiClient

gi.require_version("Gimp", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gimp, Gtk, Pango


class LoraSelector(Gtk.Box):
    def __init__(
        self, api: ApiClient, config: Gimp.ProcedureConfig, catalog: LoraCatalog,
        prompt_suffix: str, on_changed: Callable[[], None],
    ) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.api = api
        self.config = config
        self.catalog = catalog
        self.prompt_suffix = prompt_suffix
        self.on_changed = on_changed
        self.invalid_weights: set[str] = set()
        self.entries: dict[str, Gtk.Entry] = {}
        search_row = Gtk.Box(spacing=6)
        self.pack_start(search_row, False, False, 0)
        self.search = Gtk.SearchEntry(placeholder_text=_("Search LoRA name or alias"))
        search_row.pack_start(self.search, True, True, 0)
        refresh = Gtk.Button(label=_("Refresh LoRAs"))
        refresh.connect("clicked", self.refresh_catalog)
        search_row.pack_start(refresh, False, False, 0)
        self.add_button = Gtk.Button(label=_("Add LoRA"))
        self.add_button.connect("clicked", self.add_selected)
        search_row.pack_start(self.add_button, False, False, 0)
        self.error_label = Gtk.Label(xalign=0, wrap=True)
        self.pack_start(self.error_label, False, False, 0)
        self.model = Gtk.ListStore(str, str)
        self.candidates = Gtk.TreeView(model=self.model, headers_visible=True)
        for column, title in enumerate((_("LoRA name"), _("Alias"))):
            renderer = Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END)
            view_column = Gtk.TreeViewColumn(title, renderer, text=column)
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
        self.selected = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.pack_start(self.selected, False, False, 0)
        self.pack_start(Gtk.Label(label=_("Final LoRA tags"), xalign=0), False, False, 0)
        self.preview = Gtk.Label(xalign=0, wrap=True, selectable=True)
        self.preview.set_max_width_chars(70)
        self.pack_start(self.preview, False, False, 0)
        self.search.connect("search-changed", self.filter_catalog)
        self.candidates.get_selection().connect("changed", self.show_details)
        self.candidates.connect("row-activated", self.add_selected)
        self.config_handler = config.connect("notify::loras", self.reload)
        config.connect("notify::prompt", self.update_preview)
        self.filter_catalog()
        self.reload()

    def filter_catalog(self, *_args: Any) -> None:
        query = self.search.get_text().casefold()
        self.model.clear()
        for item in self.catalog.models:
            if query in item["name"].casefold() or query in item["alias"].casefold():
                self.model.append((item["name"], item["alias"]))
        self.candidates.get_selection().select_path(Gtk.TreePath.new_first())
        self.add_button.set_sensitive(len(self.model) > 0)

    def show_details(self, selection: Gtk.TreeSelection) -> None:
        model, iterator = selection.get_selected()
        if iterator is None:
            self.details.get_buffer().set_text("")
            return
        item = self.catalog.by_name[model[iterator][0]]
        self.details.get_buffer().set_text(
            item["path"] + "\n\n" + json.dumps(item["metadata"], ensure_ascii=False, indent=2),
        )

    def refresh_catalog(self, *_args: Any) -> None:
        try:
            self.api.post("/sdapi/v1/refresh-loras")
            models = self.api.get("/sdapi/v1/loras")
        except requests.RequestException as error:
            self.error_label.set_text(str(error))
            return
        self.catalog = LoraCatalog(models, self.catalog.preferred_name)
        self.error_label.set_text("")
        self.filter_catalog()
        self.update_preview()

    def reload(self, *_args: Any) -> None:
        self.items: list[LoraSelection] = json.loads(self.config.get_property("loras"))
        self.invalid_weights.clear()
        self.entries.clear()
        for row in self.selected.get_children():
            row.destroy()
        for item in self.items:
            self.add_row(item)
        self.update_preview()

    def add_selected(self, *_args: Any) -> None:
        model, iterator = self.candidates.get_selection().get_selected()
        if iterator is None:
            return
        name = model[iterator][0]
        if name in self.entries:
            self.entries[name].grab_focus()
            return
        candidate = self.catalog.by_name[name]
        item: LoraSelection = {"name": name, "alias": candidate["alias"], "weight": 1.0, "enabled": True}
        self.items.append(item)
        self.add_row(item)
        self.commit()

    def add_row(self, item: LoraSelection) -> None:
        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin=4)
        row.add(box)
        controls = Gtk.Box(spacing=6)
        box.pack_start(controls, False, False, 0)
        enabled = Gtk.CheckButton(label=_("Enabled"), active=item["enabled"])
        controls.pack_start(enabled, False, False, 0)
        text = item["name"]
        if item["alias"] != item["name"]:
            text += "\n" + _("Alias: {alias}").format(alias=item["alias"])
        label = Gtk.Label(label=text, xalign=0, ellipsize=Pango.EllipsizeMode.MIDDLE)
        label.set_tooltip_text(text)
        controls.pack_start(label, True, True, 0)
        controls.pack_start(Gtk.Label(label=_("Weight")), False, False, 0)
        entry = Gtk.Entry(text=str(item["weight"]), width_chars=9, max_width_chars=12)
        self.entries[item["name"]] = entry
        controls.pack_start(entry, False, False, 0)
        remove = Gtk.Button(label=_("Remove"))
        controls.pack_start(remove, False, False, 0)
        error_label = Gtk.Label(xalign=0, wrap=True)
        error_label.set_no_show_all(True)
        box.pack_start(error_label, False, False, 0)
        enabled.connect("toggled", self.toggle, item)
        entry.connect("changed", self.change_weight, item, error_label)
        remove.connect("clicked", self.remove, item, row)
        self.selected.add(row)
        row.show_all()

    def toggle(self, button: Gtk.ToggleButton, item: LoraSelection) -> None:
        item["enabled"] = button.get_active()
        self.commit()

    def change_weight(self, entry: Gtk.Entry, item: LoraSelection, error_label: Gtk.Label) -> None:
        try:
            weight = parse_weight(entry.get_text())
        except ValueError as error:
            self.invalid_weights.add(item["name"])
            error_label.set_text(str(error))
            error_label.show()
            self.update_preview()
            self.on_changed()
            return
        self.invalid_weights.discard(item["name"])
        error_label.hide()
        item["weight"] = weight
        self.commit()

    def remove(self, _button: Gtk.Button, item: LoraSelection, row: Gtk.ListBoxRow) -> None:
        self.items.remove(item)
        del self.entries[item["name"]]
        self.invalid_weights.discard(item["name"])
        row.destroy()
        self.commit()

    def commit(self) -> None:
        self.config.handler_block(self.config_handler)
        self.config.set_property("loras", json.dumps(self.items, ensure_ascii=False))
        self.config.handler_unblock(self.config_handler)
        self.update_preview()
        self.on_changed()

    def update_preview(self, *_args: Any) -> None:
        if self.invalid_weights:
            self.preview.set_text("")
            return
        _, tags = compose_prompt(self.config.get_property("prompt"), self.prompt_suffix, self.items, self.catalog)
        self.preview.set_text(" ".join(tags))
