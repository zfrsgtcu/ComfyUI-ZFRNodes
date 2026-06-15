import os
import io
import base64

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

from .clip_types import clip_type_input


# Bu node'un desteklediği maksimum referans görsel sayısı. Frontend (web/zfrnodes.js)
# da aynı sınırı kullanır; ikisi senkron kalmalı.
MAX_REFERENCE_IMAGES = 8


class SimpleImageGeneratorMultiple:
    """
    SimpleImageGenerator'ın çoklu referans alabilen versiyonu.

    Üç durum, aynı node:
      - Referans YOK   -> text_to_image: boş latent + denoise ile sıfırdan üretir.
      - 1 referans VAR  -> image_to_image: tek referansı ReferenceLatent ile enjekte eder.
      - N referans VAR  -> birden çok referans aynı positive conditioning'e
        ReferenceLatent olarak sırayla eklenir (Flux2 çoklu referans edit mekanizması).

    Tek bir "reference_images" girişi alır: içine bir IMAGE batch ([N,H,W,C])
    bağlanır (örn. Reference Image Loader'ın batch çıkışı). Node bu batch'i
    arkada image 1, image 2, ... olarak otomatik böler (en fazla 8). Tek tek
    slot bağlamaya gerek yoktur. Hiç referans yoksa düz text_to_image çalışır.
    Çalıştıktan sonra kullanılan referansların küçük önizlemeleri node üstünde
    bir tabloda gösterilir (frontend: web/zfrnodes.js).

    Sampling mantığı SimpleImageGenerator ile birebir aynıdır.
    """

    @classmethod
    def INPUT_TYPES(cls):
        # Tek bir "reference_images" girişi: içine bir IMAGE batch ([N,H,W,C])
        # bağlanır (örn. Reference Image Loader'ın batch çıkışı). Kaç görsel
        # gelirse gelsin (tek veya çoklu) node arkada otomatik olarak N ayrı
        # referansa böler — image 1, image 2, ... sırasıyla. Tek tek slot
        # bağlamaya gerek yoktur.
        optional = {
            # Bağlanırsa image_to_image (düzenleme), boş bırakılırsa text_to_image.
            # Her iki modda da referansın EN-BOY oranı korunur — germe/çekme YOK.
            #   match_first_reference : çıktı boyutu 1. referansın oranını/boyutunu baz alır
            #   fit_to_width_height   : oranı koruyarak girilen width x height kutusuna sığdırır
            "reference_size_mode": (
                ["match_first_reference", "fit_to_width_height"],
                {"default": "match_first_reference"},
            ),
            "reference_images": ("IMAGE",),
            # Üretilen görseli diske kaydet (Story Frame Generator ile aynı mantık).
            "save_to_disk": ("BOOLEAN", {"default": False}),
            "output_subdir": ("STRING", {"default": "simple_image"}),
            "filename_prefix": ("STRING", {"default": "image"}),
        }

        return {
            "required": {
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
                "seed_mode": (["random", "fixed"], {"default": "random"}),
            },
            "optional": optional,
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
        # append=True ile birden çok referans latent'i sırayla eklenebilir.
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

    def _resize_to(self, image, width, height, upscale_method="lanczos"):
        if int(image.shape[2]) == width and int(image.shape[1]) == height:
            return image
        samples = image.movedim(-1, 1)
        s = comfy.utils.common_upscale(samples, width, height, upscale_method, "disabled")
        return s.movedim(1, -1)

    def _fit_keep_aspect(self, image, target_w, target_h, upscale_method="lanczos"):
        """
        Referansın EN-BOY oranını koruyarak target_w x target_h alanına
        (bounding box) sığdıracak boyuta ölçekler. Görsel GERİLMEZ; çıktı
        boyutu referans oranına uyar. Sonuç 8'e bölünebilir yapılır (latent
        uyumu için).

        Örn: 768x960 referans + 960x1200 hedef -> oran 0.8 korunur,
        kutuya sığan en büyük boyut seçilir, deformasyon olmaz.
        """
        src_h, src_w = int(image.shape[1]), int(image.shape[2])
        if src_w == 0 or src_h == 0:
            return image

        # Oranı koruyarak hedef kutuya sığdır (içine tam oturan en büyük ölçek),
        # sonra en yakın 8'in katına yuvarla (latent boyut uyumu).
        scale = min(target_w / src_w, target_h / src_h)
        new_w = self._round8(src_w * scale)
        new_h = self._round8(src_h * scale)

        return self._resize_to(image, new_w, new_h, upscale_method)

    @staticmethod
    def _round8(v):
        """v'yi en YAKIN 8'in katına yuvarlar (.5 yukarı; min 8)."""
        return max(8, int((float(v) + 4) // 8) * 8)

    def _align8(self, image):
        """Görseli en yakın 8'in katı boyuta hizalar (latent uyumu). Oran ~korunur."""
        h, w = int(image.shape[1]), int(image.shape[2])
        return self._resize_to(image, self._round8(w), self._round8(h))

    @staticmethod
    def _save_image(image, output_subdir, filename_prefix):
        """
        Üretilen görseli ([1,H,W,3]) diske PNG olarak kaydeder. Story Frame
        Generator ile aynı mantık: output_subdir mutlak değilse ComfyUI output
        klasörü altına alınır. Çakışmayı önlemek için artan sayı kullanılır.
        Kaydedilen dosyanın yolunu döndürür (hata olursa None).
        """
        try:
            out_dir = output_subdir or "simple_image"
            if not os.path.isabs(out_dir):
                out_dir = os.path.join(folder_paths.get_output_directory(), out_dir)
            os.makedirs(out_dir, exist_ok=True)

            prefix = filename_prefix or "image"
            # Mevcut dosyalarla çakışmayacak ilk numarayı bul.
            idx = 0
            while True:
                path = os.path.join(out_dir, f"{prefix}_{idx:05d}.png")
                if not os.path.exists(path):
                    break
                idx += 1

            arr = (image[0].detach().cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
            Image.fromarray(arr[:, :, :3], "RGB").save(path)
            return path
        except Exception:
            return None

    @staticmethod
    def _ref_thumbnail(image, max_side=96):
        """
        Tek bir referans tensörünü ([1,H,W,C]) küçük bir PNG data-URL'ye çevirir.
        Frontend üstteki önizleme tablosunda gösterir. Hata olursa None döner.
        """
        try:
            arr = image[0].detach().cpu().numpy()
            arr = (arr * 255.0).clip(0, 255).astype(np.uint8)
            # RGBA/RGB ikisini de destekle.
            mode = "RGBA" if arr.shape[-1] == 4 else "RGB"
            img = Image.fromarray(arr[:, :, :4] if mode == "RGBA" else arr[:, :, :3], mode)
            img.thumbnail((max_side, max_side))
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("ascii")
            return f"data:image/png;base64,{b64}"
        except Exception:
            return None

    @staticmethod
    def _split_reference_batch(images):
        """
        Bir IMAGE batch tensörünü ([N,H,W,C]) tek tek referanslara böler:
        image 1, image 2, ... her biri [1,H,W,C]. None ise boş liste döner.
        Tek görsel (N=1) gelse de sorunsuz çalışır.
        """
        if images is None:
            return []
        # Beklenen şekil [N,H,W,C]. Tek görsel [1,H,W,C] zaten N=1.
        try:
            n = int(images.shape[0])
        except Exception:
            return []
        return [images[i:i + 1] for i in range(n)]

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
        reference_size_mode="match_first_reference",
        reference_images=None,
        save_to_disk=False,
        output_subdir="simple_image",
        filename_prefix="image",
        **kwargs,
    ):
        import random

        # Tek "reference_images" girişindeki IMAGE batch'ini ([N,H,W,C]) tek tek
        # referanslara böl: image 1, image 2, ... her biri [1,H,W,C]. Böylece
        # kullanıcı tek bir batch bağlar, node arkada otomatik parçalar.
        references = self._split_reference_batch(reference_images)
        # Geriye dönük uyumluluk: eski workflow'larda reference_image_N kaldıysa
        # onları da sona ekle (kwargs ile gelir).
        for i in range(1, MAX_REFERENCE_IMAGES + 1):
            ref = kwargs.get(f"reference_image_{i}")
            if ref is not None:
                references.extend(self._split_reference_batch(ref))

        references = references[:MAX_REFERENCE_IMAGES]
        has_reference = len(references) > 0
        ref_previews = []  # frontend önizleme tablosu (t2i'de boş kalır)
        prompt_text = self._prepend_trigger(trigger_words, prompt)

        cur_seed = seed if seed_mode == "fixed" else random.randint(0, 0xffffffffffffffff)

        model, vae, clip = self._load_models(unet_name, vae_name, clip_name, clip_type)
        model = self._apply_lora(model, lora_name, lora_strength)

        positive = self._encode(clip, prompt_text)

        ref_latents = []  # bellek temizliği için tut

        if not has_reference:
            # ---- text_to_image ----
            out_w, out_h = width, height
            positive = self._flux_guidance(positive, guidance)
            negative = self._zero_out(positive)
            latent = self._empty_latent(out_w, out_h)
            mode_label = "text_to_image"
        else:
            # ---- image_to_image (bir veya birden çok referansı düzenle) ----
            # ÇIKTI BOYUTU moda göre belirlenir:
            #   match_first_reference -> 1. referansın ham genişlik x yüksekliği
            #   fit_to_width_height   -> kullanıcının girdiği width x height
            # Her iki modda da GERME/ÇEKME YOK.
            if reference_size_mode == "fit_to_width_height":
                out_w = self._round8(width)
                out_h = self._round8(height)
            else:  # match_first_reference
                aligned0 = self._align8(references[0])
                out_h, out_w = int(aligned0.shape[1]), int(aligned0.shape[2])

            # ÖNEMLİ: Flux2 her referansı conditioning'e AYRI bir ReferenceLatent
            # olarak ekler (model_base.py CONDList). Referansların aynı boyutta
            # olması GEREKMEZ.
            #   - match_first_reference: 1. referans çıktı boyutunun ta kendisidir;
            #     oranı çıktıyla aynı olduğu için doğrudan out_w x out_h'a ölçeklenir
            #     (germe olmaz, oran zaten birebir aynı). Diğerleri oran koruyarak sığar.
            #   - fit_to_width_height: tüm referanslar oran koruyarak out_w x out_h'a sığar.
            for idx, ref_img in enumerate(references):
                if idx == 0 and reference_size_mode != "fit_to_width_height":
                    ref = self._resize_to(ref_img, out_w, out_h)
                else:
                    ref = self._fit_keep_aspect(ref_img, out_w, out_h)
                thumb = self._ref_thumbnail(ref_img)
                if thumb:
                    ref_previews.append(thumb)
                ref_latent = self._vae_encode(vae, ref)
                ref_latents.append(ref_latent)
                positive = self._reference_latent(positive, ref_latent)

            positive = self._flux_guidance(positive, guidance)
            negative = self._zero_out(positive)
            latent = self._empty_latent(out_w, out_h)
            mode_label = f"image_to_image (x{len(references)} ref | {reference_size_mode})"

        (out_latent,) = nodes.common_ksampler(
            model, cur_seed, steps, cfg, sampler_name, scheduler,
            positive, negative, latent, denoise=denoise,
        )
        image = self._vae_decode(vae, out_latent["samples"])

        log = f"{mode_label} | {out_w}x{out_h} | seed={cur_seed}"

        # ---- diske kaydet (opsiyonel) ----
        if save_to_disk:
            saved_path = self._save_image(image, output_subdir, filename_prefix)
            if saved_path:
                log += f" | saved: {saved_path}"

        # Bellek temizliği.
        del positive, negative, latent, out_latent
        for rl in ref_latents:
            del rl
        comfy.model_management.soft_empty_cache()

        # ui.ref_previews -> frontend onExecuted ile alır, üstteki tabloyu çizer.
        return {"ui": {"ref_previews": ref_previews}, "result": (image, log)}
