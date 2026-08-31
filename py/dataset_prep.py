"""
Dataset Prep — bir klasördeki görselleri (Reference Image Loader (Path) ile
sağlanan IMAGE batch) tek tek işleyip görsel dataset'i üretir.

Simple Image Generator (Multiple) ile aynı üretim mantığı (aynı loader'lar,
LoRA, sampler ayarları, Flux2 ReferenceLatent), tek farkı: tek bir görsel
yerine girişteki BATCH'in HER karesini sırayla işler ve hepsini diske kaydeder.

İki mod:
  - image_to_image: her giriş görseli REFERANS alınır, promptla yeni görsel üretilir
    (indirilen resimleri ortak bir stile/dönüşüme sokmak — dataset hazırlama).
  - text_to_image : giriş görselleri yok sayılır; prompt'tan görsel sayısı kadar
    (veya num_images) bağımsız görsel üretilir.

Her görsel için seed otomatik değişir (seed_mode=increment varsayılan), böylece
çıktılar çeşitlenir. save_to_disk her zaman aktiftir; çıktı klasörü serbesttir.
"""

import os

import numpy as np
import torch
from PIL import Image

import comfy.sd
import comfy.utils
import comfy.samplers
import comfy.model_management
import node_helpers
import folder_paths

import nodes  # common_ksampler, loaders

from .clip_types import clip_type_input


class DatasetPrep:
    """
    Klasördeki görselleri toplu işleyip dataset üretir. Giriş bir IMAGE batch'tir
    (Reference Image Loader (Path) çıkışı); batch'in her karesi tek tek işlenir.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE",),
                "mode": (["image_to_image", "text_to_image"], {"default": "image_to_image"}),
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "unet_name": (folder_paths.get_filename_list("diffusion_models"),),
                "vae_name": (folder_paths.get_filename_list("vae"),),
                "clip_name": (folder_paths.get_filename_list("text_encoders"),),
                "clip_type": clip_type_input("flux2"),
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
                "seed_mode": (["increment", "fixed", "random"], {"default": "increment"}),
                # i2i: çıktı boyutu — match_reference (her görselin oranı) veya
                # fit_to_width_height (width x height kutusuna oran koruyarak sığdır).
                "reference_size_mode": (
                    ["match_reference", "fit_to_width_height"],
                    {"default": "match_reference"},
                ),
                # text_to_image modunda üretilecek görsel sayısı (0 = giriş sayısı kadar).
                "num_images": ("INT", {"default": 0, "min": 0, "max": 100000}),
                # Çıktı klasörü. Mutlak yol ise oraya, değilse ComfyUI output altına.
                "output_dir": ("STRING", {"default": "dataset"}),
                "filename_prefix": ("STRING", {"default": "data"}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING", "INT")
    RETURN_NAMES = ("images", "log", "count")
    OUTPUT_NODE = True
    FUNCTION = "run"
    CATEGORY = "zfr-nodes"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    # ---------------- yükleme / conditioning (Simple Multiple ile aynı) ----------------

    def _load_models(self, unet_name, vae_name, clip_name, clip_type):
        model = nodes.UNETLoader().load_unet(unet_name, "default")[0]
        vae = nodes.VAELoader().load_vae(vae_name)[0]
        clip = nodes.CLIPLoader().load_clip(clip_name, clip_type, "default")[0]
        return model, vae, clip

    def _apply_lora(self, model, lora_name, strength):
        if lora_name in (None, "None", "") or strength == 0:
            return model
        return nodes.LoraLoaderModelOnly().load_lora_model_only(model, lora_name, strength)[0]

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

    @staticmethod
    def _round8(v):
        return max(8, int((float(v) + 4) // 8) * 8)

    def _resize_to(self, image, width, height, upscale_method="lanczos"):
        if int(image.shape[2]) == width and int(image.shape[1]) == height:
            return image
        s = comfy.utils.common_upscale(
            image.movedim(-1, 1), width, height, upscale_method, "disabled"
        )
        return s.movedim(1, -1)

    def _fit_keep_aspect(self, image, target_w, target_h):
        src_h, src_w = int(image.shape[1]), int(image.shape[2])
        if src_w == 0 or src_h == 0:
            return image
        scale = min(target_w / src_w, target_h / src_h)
        return self._resize_to(image, self._round8(src_w * scale), self._round8(src_h * scale))

    def _align8(self, image):
        h, w = int(image.shape[1]), int(image.shape[2])
        return self._resize_to(image, self._round8(w), self._round8(h))

    def _vae_encode(self, vae, image):
        return vae.encode(image[:, :, :, :3])

    def _vae_decode(self, vae, samples):
        return vae.decode(samples)

    def _empty_latent(self, width, height):
        return nodes.EmptyLatentImage().generate(width, height, 1)[0]

    @staticmethod
    def _split_batch(images):
        if images is None:
            return []
        try:
            n = int(images.shape[0])
        except Exception:
            return []
        return [images[i:i + 1] for i in range(n)]

    def _save(self, image, out_dir, prefix, idx):
        try:
            os.makedirs(out_dir, exist_ok=True)
            path = os.path.join(out_dir, f"{prefix}_{idx:05d}.png")
            arr = (image[0].detach().cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
            Image.fromarray(arr[:, :, :3], "RGB").save(path)
            return path
        except Exception:
            return None

    # ---------------- ana ----------------

    def run(
        self,
        images,
        mode,
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
        reference_size_mode="match_reference",
        num_images=0,
        output_dir="dataset",
        filename_prefix="data",
    ):
        import random

        refs = self._split_batch(images)

        # Çıktı klasörü çöz.
        out_dir = output_dir or "dataset"
        if not os.path.isabs(out_dir):
            out_dir = os.path.join(folder_paths.get_output_directory(), out_dir)

        prompt_text = self._prepend_trigger(trigger_words, prompt)

        # Modelleri BİR KEZ yükle, tüm görseller için kullan.
        base_model, vae, clip = self._load_models(unet_name, vae_name, clip_name, clip_type)
        model = self._apply_lora(base_model, lora_name, lora_strength)
        base_positive = self._encode(clip, prompt_text)

        # Kaç görsel üretilecek?
        if mode == "text_to_image":
            total = num_images if num_images and num_images > 0 else max(1, len(refs))
        else:  # image_to_image
            total = len(refs)
            if total == 0:
                empty = torch.zeros((1, height, width, 3), dtype=torch.float32)
                return (empty, "No input images for image_to_image mode.", 0)

        results = []
        log_lines = [f"Dataset Prep: mode={mode}, {total} image(s) -> {out_dir}"]

        for i in range(total):
            # Seed.
            if seed_mode == "fixed":
                cur_seed = seed
            elif seed_mode == "random":
                cur_seed = random.randint(0, 0xffffffffffffffff)
            else:  # increment
                cur_seed = (seed + i) & 0xffffffffffffffff

            positive = base_positive
            ref_latent = None

            if mode == "image_to_image":
                ref_img = refs[i]
                if reference_size_mode == "fit_to_width_height":
                    out_w, out_h = self._round8(width), self._round8(height)
                    ref = self._fit_keep_aspect(ref_img, out_w, out_h)
                else:  # match_reference
                    ref = self._align8(ref_img)
                    out_h, out_w = int(ref.shape[1]), int(ref.shape[2])
                ref_latent = self._vae_encode(vae, ref)
                positive = self._reference_latent(positive, ref_latent)
                mode_label = "i2i"
            else:
                out_w, out_h = self._round8(width), self._round8(height)
                mode_label = "t2i"

            positive = self._flux_guidance(positive, guidance)
            negative = self._zero_out(positive)
            latent = self._empty_latent(out_w, out_h)

            (out_latent,) = nodes.common_ksampler(
                model, cur_seed, steps, cfg, sampler_name, scheduler,
                positive, negative, latent, denoise=denoise,
            )
            image = self._vae_decode(vae, out_latent["samples"])

            saved = self._save(image, out_dir, filename_prefix, i)
            results.append(image.detach().cpu())
            log_lines.append(
                f"[{i + 1}/{total}] {mode_label} {out_w}x{out_h} seed={cur_seed}"
                + (f" saved={os.path.basename(saved)}" if saved else " (save failed)")
            )

            # Bellek temizliği.
            del positive, negative, latent, out_latent
            if ref_latent is not None:
                del ref_latent
            comfy.model_management.soft_empty_cache()

        # Önizleme için tek batch (hepsini ilk görselin boyutuna getir).
        if results:
            th, tw = int(results[0].shape[1]), int(results[0].shape[2])
            norm = [r if (int(r.shape[1]) == th and int(r.shape[2]) == tw)
                    else self._resize_to(r, tw, th) for r in results]
            batch = torch.cat(norm, dim=0)
        else:
            batch = torch.zeros((1, height, width, 3), dtype=torch.float32)

        log = "\n".join(log_lines)
        return (batch, log, len(results))
