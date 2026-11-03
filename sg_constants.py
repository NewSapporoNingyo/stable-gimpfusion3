# IMPORTANT!
# Strings in this file should NOT be translated
# They should be kept in English to use in SD API

AUTHOR = "SHSMAD"

STABLE_GIMPFUSION_DEFAULT_SETTINGS = {
    "sampler_name": "Euler a",
    "denoising_strength": 0.8,
    "cfg_scale": 7.5,
    "steps": 50,
    "width": 512,
    "height": 512,
    "prompt": "",
    "negative_prompt": "",
    "batch_size": 1,
    "mask_blur": 4,
    "seed": -1,
    "api_base": "http://127.0.0.1:7860",
    "model": "",
    "models": [],
    "cn_models": [],
    "sd_model_checkpoint": None,
    "is_server_running": False,
    "panel_state": {
        "parameters": None,
        "preset": "",
        "width": 480,
        "height": 800,
        "notification_toast": True,
    },
}

RESIZE_MODES = [
    "Just Resize",
    "Crop And Resize",
    "Resize And Fill",
    "Just Resize (Latent Upscale)",
]

CONTROL_MODES = [
    "Balanced",
    "My prompt is more important",
    "ControlNet is more important",
]

CONTROLNET_RESIZE_MODES = [
    "Just Resize",
    "Scale to Fit (Inner Fit)",
    "Envelope (Outer Fit)",
]

INPAINT_FILL_MODES = [
    "fill", "original", "latent noise", "latent nothing",
]

INSERT_MODES = [
    "Resize to selection",
    "Insert as is",
    "Aspect fill",
    "Aspect fit",
    "Use selection size",
]
