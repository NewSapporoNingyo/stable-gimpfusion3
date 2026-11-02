from sg_i18n import _
from sg_plugins.generation_base import GenerationPluginBase


class Image2imagePlugin(GenerationPluginBase):
    menu_path = "<Image>/GimpFusion"
    menu_label = _("Image to image")
    description = _("Generate image based on other image")
    initial_mode = "img2img"
