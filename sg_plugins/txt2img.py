from sg_i18n import _
from sg_plugins.generation_base import GenerationPluginBase


class Txt2imagePlugin(GenerationPluginBase):
    menu_path = "<Image>/GimpFusion"
    menu_label = _("Text to image")
    description = _("Generate image from text")
    initial_mode = "txt2img"
