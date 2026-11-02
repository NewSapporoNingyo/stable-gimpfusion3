from sg_i18n import _
from sg_plugins.generation_base import GenerationPluginBase


class InpaintingPlugin(GenerationPluginBase):
    menu_path = "<Image>/GimpFusion"
    menu_label = _("Inpainting")
    description = _("Inpainting in existing image")
    initial_mode = "inpaint"
