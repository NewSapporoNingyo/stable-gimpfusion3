from __future__ import annotations

from gi.repository import Gimp, GObject

from sg_constants import INSERT_MODES
from sg_i18n import _
from sg_utils import make_choice_from_list


def PLUGIN_FIELDS_CHECKPOINT(
    procedure: Gimp.Procedure,
    models: list[str],
    selected_model: str | None,
    sd_modules: list[str],
) -> None:
    procedure.add_choice_argument(
        "model",
        _("Model"),
        _("Model to use for inference"),
        make_choice_from_list(models),
        selected_model if selected_model in models else models[0],
        GObject.ParamFlags.READWRITE,
    )

    FLUX_ENCODERS_MODES = ["Autoguess", "Never add", "Always add"]
    procedure.add_choice_argument(
        "flux_encoders_mode",
        _("Add VAE and text encoders for Flux"),
        _(
            "Flux additional modules:\n"
            "Autoguess: add the listed modules for Flux or GGUF model names.\n"
            "Never add: use an empty additional-module list.\n"
            "Always add: use the listed modules.",
        ),
        make_choice_from_list(FLUX_ENCODERS_MODES),
        FLUX_ENCODERS_MODES[0],
        GObject.ParamFlags.READWRITE,
    )

    guessed_modules = [
        module
        for module in sd_modules
        if (
            module.rsplit("/", 1)[-1]
            in (
                "ae.safetensors",
                "clip_l.safetensors",
                "t5xxl_fp8_e4m3fn.safetensors",
            )
            or "flux" in module.lower()
            and ("/vae/" in module.lower() or "/text_encoder/" in module.lower())
        )
    ]

    procedure.add_string_argument(
        "flux_encoders",
        _("Flux VAEs and text encoders"),
        _("Flux VAEs and text encoders to use for Flux-based models"),
        "\n".join(guessed_modules),
        GObject.ParamFlags.READWRITE,
    )


def PLUGIN_FIELDS_COMMON(procedure: Gimp.Procedure, samplers: list[str], selected_sampler: str) -> None:
    procedure.add_string_argument(
        "prompt",
        _("Prompt"),
        _("A text string that describes the image you want to generate"),
        "",
        GObject.ParamFlags.READWRITE,
    )
    procedure.add_string_argument(
        "negative_prompt",
        _("Negative Prompt"),
        _("Features to reduce in the generated image"),
        "",
        GObject.ParamFlags.READWRITE,
    )
    procedure.add_double_argument(
        "seed",
        _("Seed"),
        _("Seed: -1 for random, 0 or a positive integer for a fixed result"),
        -1,
        4294967295,
        -1,
        GObject.ParamFlags.READWRITE,
    )
    procedure.add_int_argument(
        "batch_size",
        _("Candidates"),
        _("Number of candidate images generated in one batch"),
        1,
        20,
        1,
        GObject.ParamFlags.READWRITE,
    )
    procedure.add_int_argument(
        "steps",
        _("Steps"),
        _("Number of sampling steps; more steps increase generation time"),
        5,
        150,
        20,
        GObject.ParamFlags.READWRITE,
    )
    procedure.add_int_argument(
        "mask_blur",
        _("Mask Blur"),
        _("Gaussian blur radius in pixels on both sides of inpainting mask edges; applies to inpaint"),
        0,
        64,
        4,
        GObject.ParamFlags.READWRITE,
    )
    procedure.add_int_argument(
        "width",
        _("Width"),
        _("Width of the image you want to generate"),
        64,
        2048,
        512,
        GObject.ParamFlags.READWRITE,
    )
    procedure.add_int_argument(
        "height",
        _("Height"),
        _("Height of the image that you want to generate"),
        64,
        2048,
        512,
        GObject.ParamFlags.READWRITE,
    )
    procedure.add_double_argument(
        "cfg_scale",
        _("CFG Scale"),
        _("Strength of prompt guidance during sampling"),
        1,
        30,
        7,
        GObject.ParamFlags.READWRITE,
    )
    procedure.add_double_argument(
        "denoising_strength",
        _("Denoising Strength"),
        _("Amount of change to the source image in img2img and inpaint; higher values allow larger changes"),
        0,
        1,
        0.75,
        GObject.ParamFlags.READWRITE,
    )
    procedure.add_choice_argument(
        "sampler_index",
        _("Sampler"),
        _("Sampler to use"),
        make_choice_from_list(samplers),
        selected_sampler,
        GObject.ParamFlags.READWRITE,
    )
    procedure.add_boolean_argument(
        "restore_faces",
        _("Restore faces"),
        _("Use GFPGAN / CodeFormer to restore faces"),
        False,
        GObject.ParamFlags.READWRITE,
    )
    procedure.add_boolean_argument(
        "tiling",
        _("Tiling"),
        _("Generate a texture with seamless edges for tiling"),
        False,
        GObject.ParamFlags.READWRITE,
    )

    procedure.add_choice_argument(
        "insert_mode",
        _("Insert mode"),
        _(
            "Placement in txt2img:\n"
            "Resize to selection: stretch to the selection dimensions.\n"
            "Insert as is: keep the generated dimensions.\n"
            "Aspect fill: scale proportionally to cover the selection.\n"
            "Aspect fit: scale proportionally to fit inside the selection.\n"
            "Use selection size: generate at the selection dimensions rounded to multiples of 8.\n"
            "Results are placed at the selection top-left corner.",
        ),
        make_choice_from_list(INSERT_MODES),
        INSERT_MODES[0],
        GObject.ParamFlags.READWRITE,
    )


def PLUGIN_FIELDS_CONTROLNET_OPTIONS(procedure: Gimp.Procedure) -> None:
    procedure.add_boolean_argument(
        "cn1_enabled",
        _("Enable ControlNet 1"),
        _("Enable ControlNet 1 for generation"),
        False,
        GObject.ParamFlags.READWRITE,
    )
    procedure.add_layer_argument(
        "cn1_layer",
        _("ControlNet 1 Layer"),
        _("ControlNet 1 Layer for generation"),
        True,
        GObject.ParamFlags.READWRITE,
    )
    procedure.add_boolean_argument(
        "cn2_enabled",
        _("Enable ControlNet 2"),
        _("Enable ControlNet 2 for generation"),
        False,
        GObject.ParamFlags.READWRITE,
    )
    procedure.add_layer_argument(
        "cn2_layer",
        _("ControlNet 2 Layer"),
        _("ControlNet 2 Layer for generation"),
        True,
        GObject.ParamFlags.READWRITE,
    )
    procedure.add_boolean_argument(
        "cn_skip_annotator_layers",
        _("Import candidates only"),
        _(
            "Enabled: import generated candidates. Disabled: also import ControlNet preprocessing or reference images. "
            "Applies to all three modes.",
        ),
        True,
        GObject.ParamFlags.READWRITE,
    )


def PLUGIN_FIELDS_RESIZE_MODE(procedure: Gimp.Procedure, resize_modes: list[str]) -> None:
    procedure.add_choice_argument(
        "resize_mode",
        _("Resize Mode"),
        _(
            "Resizing in img2img and inpaint:\n"
            "Just Resize: stretch to the requested dimensions.\n"
            "Crop And Resize: scale proportionally to cover the frame, then crop.\n"
            "Resize And Fill: fit inside the frame and extend the edge colors.\n"
            "Just Resize (Latent Upscale): resize in latent space.",
        ),  # noqa: E501
        make_choice_from_list(resize_modes),
        resize_modes[0],
        GObject.ParamFlags.READWRITE,
    )


def PLUGIN_FIELDS_INPAINTING(procedure: Gimp.Procedure, inpaint_fill_modes: list[str]) -> None:
    procedure.add_boolean_argument(
        "invert_mask",
        _("Invert Mask"),
        _("Enabled: repaint the black mask area. Disabled: repaint the white mask area."),
        False,
        GObject.ParamFlags.READWRITE,
    )
    procedure.add_boolean_argument(
        "inpaint_full_res",
        _("Inpaint area"),
        _(
            "Whole picture samples the entire source; "
            "Only masked samples the mask area and composites it into the source",
        ),
        False,
        GObject.ParamFlags.READWRITE,
    )
    procedure.add_int_argument(
        "inpaint_full_res_padding",
        _("Only masked padding, pixels"),
        _("Context added around the mask before sampling in Only masked mode"),
        0,
        256,
        32,
        GObject.ParamFlags.READWRITE,
    )
    procedure.add_choice_argument(
        "inpainting_fill",
        _("Mask fill mode"),
        _(
            "Initial content in the inpainting mask:\n"
            "fill: fill using surrounding colors.\n"
            "original: use the source content.\n"
            "latent noise: initialize with seeded latent noise.\n"
            "latent nothing: initialize the masked latent values to zero.",
        ),  # noqa: E501
        make_choice_from_list(inpaint_fill_modes),
        "original",
        GObject.ParamFlags.READWRITE,
    )


def PLUGIN_FIELDS_CONTROLNET(
    procedure: Gimp.Procedure,
    cn_modules: list[str],
    cn_models: list[str],
    cn_resize_modes: list[str],
    control_modes: list[str],
    prefix: str = "",
) -> None:
    for name, label, help_text, choices in (
        ("module", _("Module"), _("ControlNet preprocessor applied to the input layer"), cn_modules),
        ("model", _("Model"), _("ControlNet model paired with the preprocessor"), cn_models),
        ("resize_mode", _("Resize Mode"), _("Fit the ControlNet input to the generation frame"), cn_resize_modes),
        ("control_mode", _("Control Mode"), _("Balance prompt guidance and ControlNet guidance"), control_modes),
    ):
        procedure.add_choice_argument(
            prefix + name,
            label,
            help_text,
            make_choice_from_list(choices),
            choices[0],
            GObject.ParamFlags.READWRITE,
        )
    for name, label, help_text, minimum, maximum, value in (
        ("weight", _("Weight"), _("Strength of the ControlNet condition"), 0, 2, 1),
        (
            "guidance_start",
            _("Guidance Start (T)"),
            _("Sampling progress at which ControlNet starts; 0 is the beginning"),
            0,
            1,
            0,
        ),
        ("guidance_end", _("Guidance End (T)"), _("Sampling progress at which ControlNet ends; 1 is the end"), 0, 1, 1),
        (
            "threshold_a",
            _("Threshold A"),
            _("First preprocessor parameter; meaning and range depend on the selected module"),
            -1,
            2048,
            64,
        ),
        (
            "threshold_b",
            _("Threshold B"),
            _("Second preprocessor parameter; meaning and range depend on the selected module"),
            -1,
            2048,
            64,
        ),
    ):
        procedure.add_double_argument(
            prefix + name,
            label,
            help_text,
            minimum,
            maximum,
            value,
            GObject.ParamFlags.READWRITE,
        )
    procedure.add_int_argument(
        prefix + "processor_res",
        _("Processor Resolution"),
        _("ControlNet preprocessing resolution"),
        64,
        2048,
        512,
        GObject.ParamFlags.READWRITE,
    )
