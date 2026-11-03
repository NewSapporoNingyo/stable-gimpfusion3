from __future__ import annotations

import gi

gi.require_version("GimpUi", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gimp, GimpUi, Gtk, Pango

from sg_i18n import _


def add_textarea_to_container(
    procedure: Gimp.Procedure,
    config: Gimp.ProcedureConfig,
    argument_name: str,
    container: Gtk.Container,
) -> None:
    prompt_w = Gtk.TextView.new_with_buffer(GimpUi.prop_text_buffer_new(config, argument_name, 0))
    prompt_w.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    label = Gtk.Label(_(procedure.find_argument(argument_name).nick))
    label.set_halign(Gtk.Align.START)
    container.add(label)
    label.show()

    scrolled_window = Gtk.ScrolledWindow()
    scrolled_window.add(prompt_w)
    metrics = prompt_w.get_pango_context().get_metrics()
    line_height = (metrics.get_ascent() + metrics.get_descent() + Pango.SCALE - 1) // Pango.SCALE
    scrolled_window.set_min_content_height(8 * line_height)

    container.add(scrolled_window)
    scrolled_window.show_all()
