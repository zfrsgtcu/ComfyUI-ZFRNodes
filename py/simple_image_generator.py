import math

import torch

import comfy.sd
import comfy.utils
import comfy.sample
import comfy.samplers
import comfy.model_management
import node_helpers
import folder_paths

import nodes  # common_ksampler, loaders


class SimpleImageGenerator:
    """
    Tek node içinde tek görsel üretir (prompt -> image).

    İki mod, aynı node:
      - Referans YOK  -> text_to_image: boş latent + denoise 1.0 ile sıfırdan üretir.
      - Referans VAR  -> image_to_image: verilen referans görseli ReferenceLatent ile
        positive conditioning'e enjekte ederek düzenleme yapar (Flux2 edit mekanizması).

    StoryFrameGenerator ile aynı sampling mantığını kullanır ama zincir/JSON yoktur;
    sadece tek bir prompt ve isteğe bağlı tek bir referans görsel alır.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "unet_name": (folder_paths.get_filename_list("diffusion_models"),),
                "vae_name": (folder_paths.get_filename_list("vae"),),
                "clip_name": (folder_paths.get_filename_list("text_encoders"),),
                "clip_type": (["flux2", "flux", "sd3", "sdxl", "stable_diffusion"], {"default": "flux2"}),
                "lora_name": (["None"] + folder_paths.get_filename_list("loras"),),
                "lora_strength": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                "trigger_words": ("STRING", {"multiline": False, "default": ""}),
                "width": ("INT", {"default": 960, "min": 64, "max": 8192, "step": 8}),
                "height": ("INT", {"default": 1200, "min": 64, "max": 8192, "step": 8}),
                "steps": ("INT", {"default": 8, "min": 1, "max": 200}),
                "cfg": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 30.0, "step": 0.1}),
                "guidance": ("FLOAT", {"default": 3.5, "min": 0.0, "max": 100.0, "step": 0.1}),
                "denoise": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "sampler_name": (comfy.samplers.KSampler.SAMPLERS, {"default": "euler"}),
                "scheduler": (comfy.samplers.KSampler.SCHEDULERS, {"default": "simple"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
                "seed_mode": (["random", "fixed"], {"default": "random"}),
            },
            "optional": {
                # Bağlanırsa image_to_image (düzenleme), boş bırakılırsa text_to_image.
                "reference_image": ("IMAGE",),
                "reference_megapixels": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 16.0, "step": 0.01}),
                "reference_size_mode": (["scale_to_megapixels", "match_width_height"], {"default": "scale_to_megapixels"}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "log")
    FUNCTION = "generate"
    CATEGORY = "zfr-nodes"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    # ---------------- yükleme ----------------

    def _load_models(self, unet_name, vae_name, clip_name, clip_type):
        model = nodes.UNETLoader().load_unet(unet_name, "default")[0]
        vae = nodes.VAELoader().load_vae(vae_name)[0]
        clip = nodes.CLIPLoader().load_clip(clip_name, clip_type, "default")[0]
        return model, vae, clip

    def _apply_lora(self, model, lora_name, strength):
        if lora_name in (None, "None", "") or strength == 0:
            return model
        return nodes.LoraLoaderModelOnly().load_lora_model_only(model, lora_name, strength)[0]

    # ---------------- conditioning ----------------

    def _encode(self, clip, text):
        tokens = clip.tokenize(text)
        return clip.encode_from_tokens_scheduled(tokens)

    def _flux_guidance(self, cond, guidance):
        return node_helpers.conditioning_set_values(cond, {"guidance": guidance})

    def _reference_latent(self, cond, latent_samples):
        return node_helpers.conditioning_set_values(
            cond, {"reference_latents": [latent_samples]}, append=True
        )

    def _zero_out(self, cond):
        return nodes.ConditioningZeroOut().zero_out(cond)[0]

    def _prepend_trigger(self, trigger, prompt_text):
        trigger = (trigger or "").strip()
        if not trigger:
            return prompt_text
        if not prompt_text:
            return trigger
        return f"{trigger}, {prompt_text}"

    # ---------------- görüntü <-> latent ----------------

    def _scale_to_megapixels(self, image, megapixels, upscale_method="lanczos"):
        samples = image.movedim(-1, 1)
        total = megapixels * 1024 * 1024
        scale_by = math.sqrt(total / (samples.shape[3] * samples.shape[2]))
        width = round(samples.shape[3] * scale_by)
        height = round(samples.shape[2] * scale_by)
        s = comfy.utils.common_upscale(samples, width, height, upscale_method, "disabled")
        return s.movedim(1, -1)

    def _resize_to(self, image, width, height, upscale_method="lanczos"):
        if int(image.shape[2]) == width and int(image.shape[1]) == height:
            return image
        samples = image.movedim(-1, 1)
        s = comfy.utils.common_upscale(samples, width, height, upscale_method, "disabled")
        return s.movedim(1, -1)

    def _vae_encode(self, vae, image):
        return vae.encode(image[:, :, :, :3])

    def _vae_decode(self, vae, samples):
        return vae.decode(samples)

    def _empty_latent(self, width, height):
        return nodes.EmptyLatentImage().generate(width, height, 1)[0]

    # ---------------- ana ----------------

    def generate(
        self,
        prompt,
        unet_name,
        vae_name,
        clip_name,
        clip_type,
        lora_name,
        lora_strength,
        trigger_words,
        width,
        height,
        steps,
        cfg,
        guidance,
        denoise,
        sampler_name,
        scheduler,
        seed,
        seed_mode,
        reference_image=None,
        reference_megapixels=1.0,
        reference_size_mode="scale_to_megapixels",
    ):
        import random

        has_reference = reference_image is not None
        prompt_text = self._prepend_trigger(trigger_words, prompt)

        cur_seed = seed if seed_mode == "fixed" else random.randint(0, 0xffffffffffffffff)

        model, vae, clip = self._load_models(unet_name, vae_name, clip_name, clip_type)
        model = self._apply_lora(model, lora_name, lora_strength)

        positive = self._encode(clip, prompt_text)

        if not has_reference:
            # ---- text_to_image ----
            out_w, out_h = width, height
            positive = self._flux_guidance(positive, guidance)
            negative = self._zero_out(positive)
            latent = self._empty_latent(out_w, out_h)
            mode_label = "text_to_image"
        else:
            # ---- image_to_image (referans görseli düzenle) ----
            if reference_size_mode == "match_width_height":
                ref = self._resize_to(reference_image, width, height)
            else:  # scale_to_megapixels
                ref = self._scale_to_megapixels(reference_image, reference_megapixels)
            out_h, out_w = int(ref.shape[1]), int(ref.shape[2])

            ref_latent = self._vae_encode(vae, ref)
            positive = self._reference_latent(positive, ref_latent)
            positive = self._flux_guidance(positive, guidance)
            negative = self._zero_out(positive)
            latent = self._empty_latent(out_w, out_h)
            mode_label = "image_to_image"

        (out_latent,) = nodes.common_ksampler(
            model, cur_seed, steps, cfg, sampler_name, scheduler,
            positive, negative, latent, denoise=denoise,
        )
        image = self._vae_decode(vae, out_latent["samples"])

        log = f"{mode_label} | {out_w}x{out_h} | seed={cur_seed}"

        # Bellek temizliği.
        del positive, negative, latent, out_latent
        if has_reference:
            del ref, ref_latent
        comfy.model_management.soft_empty_cache()

        return (image, log)
