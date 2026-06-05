import os
import json
import math

import numpy as np
import torch
from PIL import Image

import comfy.sd
import comfy.utils
import comfy.sample
import comfy.samplers
import comfy.model_management
import node_helpers
import folder_paths

import nodes  # common_ksampler, loaders


class StoryFrameGenerator:
    """
    Tek node içinde tüm frame zincirini üretir.

    JSON'daki frames[] sırayla işlenir:
      - frame.type == "text_to_image"  -> boş latent'ten sıfırdan görsel üretir.
      - frame.type == "image_to_image" -> BİR ÖNCEKİ frame'in çıktısını referans
        alır (Flux2 ReferenceLatent edit mekanizması) ve yeni görsel üretir.

    Böylece feedback loop graph'ta kurulamadan, döngü node İÇİNDE döner ve
    her frame bir öncekinin üzerine devam ederek tutarlı bir sahne dizisi oluşur.

    Çıktı: tüm frame'ler tek IMAGE batch + log. Ayrıca diske kaydedilir.

    Davranış, kullanıcının iki subgraph'ıyla birebir aynıdır:
      Flux2 (flux-2-klein) + Qwen CLIP (type=flux2) + LoraLoaderModelOnly,
      CLIPTextEncode -> (i2i: ReferenceLatent) -> FluxGuidance, negatif =
      ConditioningZeroOut, KSampler(euler/simple/denoise=1.0), VAEDecode.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompts_json": ("STRING", {"multiline": True, "default": ""}),
                "unet_name": (folder_paths.get_filename_list("diffusion_models"),),
                "vae_name": (folder_paths.get_filename_list("vae"),),
                "clip_name": (folder_paths.get_filename_list("text_encoders"),),
                "clip_type": (["flux2", "flux", "sd3", "sdxl", "stable_diffusion"], {"default": "flux2"}),
                "lora_name_t2i": (["None"] + folder_paths.get_filename_list("loras"),),
                "lora_strength_t2i": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),
                "trigger_words_t2i": ("STRING", {"multiline": False, "default": ""}),
                "lora_name_i2i": (["None"] + folder_paths.get_filename_list("loras"),),
                "lora_strength_i2i": ("FLOAT", {"default": 0.9, "min": -10.0, "max": 10.0, "step": 0.01}),
                "trigger_words_i2i": ("STRING", {"multiline": False, "default": ""}),
                "width": ("INT", {"default": 960, "min": 64, "max": 8192, "step": 8}),
                "height": ("INT", {"default": 1200, "min": 64, "max": 8192, "step": 8}),
                "steps": ("INT", {"default": 8, "min": 1, "max": 200}),
                "cfg": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 30.0, "step": 0.1}),
                "guidance": ("FLOAT", {"default": 3.5, "min": 0.0, "max": 100.0, "step": 0.1}),
                "denoise": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "sampler_name": (comfy.samplers.KSampler.SAMPLERS, {"default": "euler"}),
                "scheduler": (comfy.samplers.KSampler.SCHEDULERS, {"default": "simple"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
                "seed_mode": (["fixed", "increment", "random"], {"default": "random"}),
                "reference_megapixels": ("FLOAT", {"default": 1.0, "min": 0.1, "max": 16.0, "step": 0.01}),
                "i2i_size_mode": (["scale_to_megapixels", "match_first_frame"], {"default": "scale_to_megapixels"}),
            },
            "optional": {
                "save_to_disk": ("BOOLEAN", {"default": True}),
                "output_subdir": ("STRING", {"default": "story_frames"}),
                "filename_prefix": ("STRING", {"default": "frame"}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING", "INT")
    RETURN_NAMES = ("frames", "log", "frame_count")
    FUNCTION = "generate"
    CATEGORY = "zfr-nodes"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    # ---------------- JSON ----------------

    def _parse_json(self, prompts_json):
        if isinstance(prompts_json, dict):
            return prompts_json
        if isinstance(prompts_json, str):
            try:
                return json.loads(prompts_json)
            except Exception:
                return {}
        return {}

    def _prompt_to_text(self, prompt):
        if isinstance(prompt, dict):
            return "\n".join(f"{k}: {v}" for k, v in prompt.items())
        if isinstance(prompt, list):
            return "\n".join(self._prompt_to_text(p) for p in prompt)
        return str(prompt)

    def _prepend_trigger(self, trigger, prompt_text):
        # LoRA tetikleyici kelime(ler)ini prompt'un başına ekler.
        trigger = (trigger or "").strip()
        if not trigger:
            return prompt_text
        if not prompt_text:
            return trigger
        return f"{trigger}, {prompt_text}"

    # ---------------- yükleme ----------------

    def _load_models(self, unet_name, vae_name, clip_name, clip_type):
        # ComfyUI loader node'larıyla birebir aynı yükleme.
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
        # ComfyUI'nin ConditioningZeroOut'u ile birebir (pooled_output None olabilir).
        return nodes.ConditioningZeroOut().zero_out(cond)[0]

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
        # Görüntüyü tam (width, height) boyutuna getirir. Zaten o boyuttaysa
        # neredeyse maliyetsizdir; zincir boyunca boyutu sabit tutmak için kullanılır.
        if int(image.shape[2]) == width and int(image.shape[1]) == height:
            return image
        samples = image.movedim(-1, 1)
        s = comfy.utils.common_upscale(samples, width, height, upscale_method, "disabled")
        return s.movedim(1, -1)

    def _vae_encode(self, vae, image):
        # ComfyUI VAEEncode ile birebir: tek tensör döndürür ({"samples": t} değil).
        return vae.encode(image[:, :, :, :3])

    def _vae_decode(self, vae, samples):
        return vae.decode(samples)

    def _empty_latent(self, width, height):
        # ComfyUI'nin kendi EmptyLatentImage node'unu çağır: doğru kanal sayısı,
        # doğru cihaz/dtype ve "downscale_ratio_spacial" anahtarı dahil birebir
        # kullanıcının workflow'uyla aynı boş latent üretir.
        return nodes.EmptyLatentImage().generate(width, height, 1)[0]

    # ---------------- ana ----------------

    def generate(
        self,
        prompts_json,
        unet_name,
        vae_name,
        clip_name,
        clip_type,
        lora_name_t2i,
        lora_strength_t2i,
        trigger_words_t2i,
        lora_name_i2i,
        lora_strength_i2i,
        trigger_words_i2i,
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
        reference_megapixels,
        i2i_size_mode="scale_to_megapixels",
        save_to_disk=True,
        output_subdir="story_frames",
        filename_prefix="frame",
    ):
        import random

        data = self._parse_json(prompts_json)
        frames = data.get("frames", [])
        if not isinstance(frames, list) or not frames:
            empty = torch.zeros((1, height, width, 3), dtype=torch.float32)
            return (empty, "Hata: 'frames' bulunamadı veya boş.", 0)

        log_lines = []

        # Modelleri BİR KEZ yükle.
        base_model, vae, clip = self._load_models(unet_name, vae_name, clip_name, clip_type)
        # t2i ve i2i için ayrı LoRA. "None" seçilirse LoRA'sız temel model kullanılır.
        model_t2i = self._apply_lora(base_model, lora_name_t2i, lora_strength_t2i)
        model_i2i = self._apply_lora(base_model, lora_name_i2i, lora_strength_i2i)
        log_lines.append(
            f"Modeller yüklendi. {len(frames)} frame işlenecek. "
            f"t2i LoRA={lora_name_t2i}, i2i LoRA={lora_name_i2i}"
        )

        out_dir = None
        if save_to_disk:
            out_dir = output_subdir
            if not os.path.isabs(out_dir):
                out_dir = os.path.join(folder_paths.get_output_directory(), out_dir)
            os.makedirs(out_dir, exist_ok=True)

        results = []
        prev_image = None      # bir önceki frame'in IMAGE tensörü (referans için)
        i2i_w = None           # i2i zinciri boyunca SABİT genişlik (bir kez belirlenir)
        i2i_h = None           # i2i zinciri boyunca SABİT yükseklik

        for idx, frame in enumerate(frames):
            if not isinstance(frame, dict):
                continue

            ftype = frame.get("type", "text_to_image")
            prompt_text = self._prompt_to_text(frame.get("prompt"))

            is_first = (idx == 0) or (ftype == "text_to_image") or (prev_image is None)

            # LoRA tetikleyici kelimelerini moda göre prompt'un başına ekle.
            trigger = trigger_words_t2i if is_first else trigger_words_i2i
            prompt_text = self._prepend_trigger(trigger, prompt_text)

            if seed_mode == "fixed":
                cur_seed = seed
            elif seed_mode == "increment":
                cur_seed = seed + idx
            else:  # random
                cur_seed = random.randint(0, 0xffffffffffffffff)

            positive = self._encode(clip, prompt_text)

            if is_first:
                # ---- text_to_image ----
                # İlk frame kullanıcının verdiği width/height ile üretilir.
                frame_w, frame_h = width, height
                positive = self._flux_guidance(positive, guidance)
                negative = self._zero_out(positive)
                latent = self._empty_latent(frame_w, frame_h)
                model = model_t2i
                mode_label = "text_to_image"
            else:
                # ---- image_to_image (önceki frame'i referans al) ----
                # i2i boyutu zincir boyunca BİR KEZ belirlenir, sonra sabit kalır
                # (drift'i önlemek için her turda yeniden hesaplanmaz):
                #   - scale_to_megapixels: ilk i2i'de referansı MP'ye ölçekle, o boyutu sabitle
                #   - match_first_frame  : t2i çıktı boyutunu (width/height) kullan
                if i2i_w is None or i2i_h is None:
                    if i2i_size_mode == "match_first_frame":
                        i2i_w, i2i_h = width, height
                        ref = self._resize_to(prev_image, i2i_w, i2i_h)
                    else:  # scale_to_megapixels
                        ref = self._scale_to_megapixels(prev_image, reference_megapixels)
                        i2i_h, i2i_w = int(ref.shape[1]), int(ref.shape[2])
                else:
                    # Referansı sabitlenmiş boyuta getir (önceki frame zaten bu
                    # boyutta olduğundan bu çoğunlukla no-op'tur).
                    ref = self._resize_to(prev_image, i2i_w, i2i_h)

                frame_w, frame_h = i2i_w, i2i_h
                ref_latent = self._vae_encode(vae, ref)
                positive = self._reference_latent(positive, ref_latent)
                positive = self._flux_guidance(positive, guidance)
                negative = self._zero_out(positive)
                latent = self._empty_latent(frame_w, frame_h)
                model = model_i2i
                mode_label = "image_to_image"

            (out_latent,) = nodes.common_ksampler(
                model, cur_seed, steps, cfg, sampler_name, scheduler,
                positive, negative, latent, denoise=denoise,
            )

            image = self._vae_decode(vae, out_latent["samples"])  # (1,H,W,3)

            # Diske kaydet (henüz GPU'dayken).
            if save_to_disk:
                arr = (image[0].cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
                Image.fromarray(arr).save(
                    os.path.join(out_dir, f"{filename_prefix}_{idx:03d}.png")
                )

            # prev_image referans için GPU'da kalsın; sonuç batch'i RAM'de biriksin.
            prev_image = image
            results.append(image.detach().cpu())

            log_lines.append(
                f"[{idx + 1}/{len(frames)}] {mode_label} | {frame_w}x{frame_h} | seed={cur_seed}"
            )

            # ---- her tur sonrası bellek temizliği ----
            del positive, negative, latent, out_latent
            if not is_first:
                del ref, ref_latent
            comfy.model_management.soft_empty_cache()

        if not results:
            empty = torch.zeros((1, height, width, 3), dtype=torch.float32)
            return (empty, "Hiç frame üretilemedi.", 0)

        # Tek IMAGE batch'i için tüm frame'ler aynı boyutta olmalı. t2i ve i2i
        # boyutları farklı olabileceğinden (scale_to_megapixels modu), hepsini ilk
        # frame'in boyutuna getirip birleştiriyoruz. (Diske kayıt orijinal boyutta.)
        target_h, target_w = int(results[0].shape[1]), int(results[0].shape[2])
        normalized = []
        for img in results:
            if int(img.shape[1]) != target_h or int(img.shape[2]) != target_w:
                img = self._resize_to(img, target_w, target_h)
            normalized.append(img)
        batch = torch.cat(normalized, dim=0)
        log = "\n".join(log_lines)
        return (batch, log, len(results))
