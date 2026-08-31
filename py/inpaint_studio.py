"""
ZFR Inpaint Studio — tek node içinde "mini Photoshop" inpaint deneyimi.

Senaryo (tek node, arkada birden çok base node zincirlenir):

  1. Kullanıcı node İÇİNDEN resmi yükler ("image" widget'ı, image_upload=True).
     Resme sağ tıklayıp ComfyUI'nin HAZIR MaskEditor'ünü açar ve değiştirmek
     istediği alanı fırçayla boyar. Maske, yüklenen PNG'nin alpha kanalına gömülür.
  2. Aynı node üzerinde model / vae / clip / lora ve tüm inpaint + üretim ayarları
     yapılır.
  3. prompt yazılır, çalıştırılır -> sadece maskelenen alan yeniden üretilir,
     geri kalan (composite_back açıksa) orijinalden birebir korunur.

Bu node sıfırdan hiçbir algoritma icat ETMEZ; ComfyUI'nin yerleşik parçalarını
arkada zincirler:
  - Resim+maske okuma : LoadImage (alpha->mask) mantığı
  - Model yükleme      : SimpleImageGeneratorMultiple ile aynı (UNETLoader/VAELoader/CLIPLoader)
  - Inpaint cond.      : InpaintModelConditioning (nodes.py) iç mantığı inline
  - Maske büyütme      : GrowMask (scipy grey_dilation/erosion)
  - Maske yumuşatma    : FeatherMask (kenar gradyanı)
  - Differential Diff. : model.set_model_denoise_mask_function (yumuşak kaynaşma)
  - Composite back     : ImageCompositeMasked mantığı (maske dışını koru)
  - Sampling           : nodes.common_ksampler

Çıktı: (IMAGE, STRING) -> image, log.
"""

import os
import hashlib
import random

import numpy as np
import scipy.ndimage
import torch
from PIL import Image, ImageOps, ImageSequence

import comfy.utils
import comfy.samplers
import comfy.model_management
import node_helpers
import folder_paths

import nodes  # common_ksampler, UNETLoader, VAELoader, CLIPLoader, LoraLoaderModelOnly

from .clip_types import clip_type_input


class InpaintStudio:
    """
    Tek node'da: yükle + (MaskEditor ile) maskele + inpaint + üret.
    """

    @classmethod
    def INPUT_TYPES(cls):
        # Yüklenen input görselleri (LoadImage ile birebir aynı kaynak liste).
        input_dir = folder_paths.get_input_directory()
        try:
            files = [
                f for f in os.listdir(input_dir)
                if os.path.isfile(os.path.join(input_dir, f))
            ]
            files = folder_paths.filter_files_content_types(files, ["image"])
        except Exception:
            files = []

        return {
            "required": {
                # --- resim + maske (node içinden yükle + sağ tık "Open in MaskEditor") ---
                "image": (sorted(files), {"image_upload": True}),

                # --- prompt ---
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "trigger_words": ("STRING", {"multiline": False, "default": ""}),

                # --- referans aç/kapa ---
                # reference_images bağlanırsa maske bölgesine "ne ekleneceği"
                # bu referanslardan öğrenilir (Flux2 ReferenceLatent). Kapatınca
                # bağlı referanslar yok sayılır.
                "use_references": ("BOOLEAN", {"default": True}),

                # --- model grubu (Simple Image Generator (Multiple) ile aynı) ---
                "unet_name": (folder_paths.get_filename_list("diffusion_models"),),
                "vae_name": (folder_paths.get_filename_list("vae"),),
                "clip_name": (folder_paths.get_filename_list("text_encoders"),),
                "clip_type": clip_type_input("flux2"),
                "lora_name": (["None"] + folder_paths.get_filename_list("loras"),),
                "lora_strength": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.01}),

                # --- inpaint ayarları (+ bonuslar) ---
                "denoise": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}),
                "grow_mask": ("INT", {"default": 6, "min": -64, "max": 256, "step": 1}),
                "feather_mask": ("INT", {"default": 0, "min": 0, "max": 256, "step": 1}),
                "noise_mask": ("BOOLEAN", {"default": True}),
                "differential_diffusion": ("BOOLEAN", {"default": False}),
                "composite_back": ("BOOLEAN", {"default": True}),

                # --- üretim ayarları ---
                "steps": ("INT", {"default": 20, "min": 1, "max": 200}),
                "cfg": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 30.0, "step": 0.1}),
                "guidance": ("FLOAT", {"default": 3.5, "min": 0.0, "max": 100.0, "step": 0.1}),
                "sampler_name": (comfy.samplers.KSampler.SAMPLERS, {"default": "euler"}),
                "scheduler": (comfy.samplers.KSampler.SCHEDULERS, {"default": "simple"}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
                "seed_mode": (["random", "fixed"], {"default": "random"}),

                # --- çıktı ---
                "save_to_disk": ("BOOLEAN", {"default": False}),
                "output_subdir": ("STRING", {"default": "inpaint_studio"}),
                "filename_prefix": ("STRING", {"default": "inpaint"}),
            },
            "optional": {
                # Çoklu referans: bir IMAGE batch ([N,H,W,C]) bağlanır
                # (örn. Reference Image Loader). Maske bölgesine eklenecek
                # nesneler bu referanslardan öğrenilir.
                "reference_images": ("IMAGE",),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("image", "log")
    FUNCTION = "generate"
    CATEGORY = "zfr-nodes"

    @classmethod
    def IS_CHANGED(cls, image=None, seed_mode="random", **kwargs):
        # random seed modunda her çalıştırmada yeniden üret.
        if seed_mode != "fixed":
            return float("nan")
        # fixed modda yalnızca yüklenen/boyanan görsel dosyası değişince yeniden çalış.
        try:
            path = folder_paths.get_annotated_filepath(image)
            m = hashlib.sha256()
            with open(path, "rb") as f:
                m.update(f.read())
            return m.digest().hex()
        except Exception:
            return float("nan")

    @classmethod
    def VALIDATE_INPUTS(cls, image, **kwargs):
        # LoadImage ile aynı: dosyanın INPUT_TYPES listesinde OLMASINI değil,
        # gerçekten VAR olmasını kontrol et. MaskEditor maskeyi
        # "clipspace/clipspace-painted-masked-*.png [input]" olarak kaydeder; bu
        # yol başlangıçtaki düz dosya listesinde bulunmaz ama geçerlidir.
        if not folder_paths.exists_annotated_filepath(image):
            return "Invalid image file: {}".format(image)
        return True

    # ---------------- resim + maske okuma ----------------

    @staticmethod
    def _load_image_and_mask(image_name):
        """
        Yüklenen görseli (input klasöründen) IMAGE [1,H,W,3] + MASK [1,H,W]
        olarak okur. MaskEditor ile boyanan alan PNG'nin alpha kanalına gömülür;
        LoadImage ile aynı (1 - alpha) mantığıyla maskeye çevrilir. Alpha yoksa
        (hiç boyama yapılmadıysa) maske tamamen 0 döner.

        LoadImageWithFilename / LoadImage kalıbı.
        """
        image_path = folder_paths.get_annotated_filepath(image_name)
        img = node_helpers.pillow(Image.open, image_path)

        output_images = []
        output_masks = []
        w, h = None, None
        excluded_formats = ["MPO"]

        for frame in ImageSequence.Iterator(img):
            frame = node_helpers.pillow(ImageOps.exif_transpose, frame)
            if frame.mode == "I":
                frame = frame.point(lambda v: v * (1 / 255))
            rgb = frame.convert("RGB")

            if len(output_images) == 0:
                w, h = rgb.size

            if rgb.size[0] != w or rgb.size[1] != h:
                continue

            arr = np.array(rgb).astype(np.float32) / 255.0
            output_images.append(torch.from_numpy(arr)[None, ])

            if "A" in frame.getbands():
                m = np.array(frame.getchannel("A")).astype(np.float32) / 255.0
                m = 1.0 - torch.from_numpy(m)
            elif frame.mode == "P" and "transparency" in frame.info:
                m = np.array(frame.convert("RGBA").getchannel("A")).astype(np.float32) / 255.0
                m = 1.0 - torch.from_numpy(m)
            else:
                m = torch.zeros((h or 64, w or 64), dtype=torch.float32)
            output_masks.append(m.unsqueeze(0))

        if len(output_images) > 1 and img.format not in excluded_formats:
            out_image = torch.cat(output_images, dim=0)
            out_mask = torch.cat(output_masks, dim=0)
        else:
            out_image = output_images[0]
            out_mask = output_masks[0]

        # Bu node tek görselle çalışır; batch gelirse ilkini kullan.
        return out_image[:1], out_mask[:1]

    # ---------------- model yükleme (Simple Image Generator ile aynı) ----------------

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

    def _zero_out(self, cond):
        return nodes.ConditioningZeroOut().zero_out(cond)[0]

    def _reference_latent(self, cond, latent_samples):
        # Flux2 çoklu referans: her referans latent'i sırayla append edilir.
        return node_helpers.conditioning_set_values(
            cond, {"reference_latents": [latent_samples]}, append=True
        )

    @staticmethod
    def _split_reference_batch(images):
        """Bir IMAGE batch'ini ([N,H,W,C]) tek tek referanslara böler."""
        if images is None:
            return []
        try:
            n = int(images.shape[0])
        except Exception:
            return []
        return [images[i:i + 1] for i in range(n)]

    def _fit_keep_aspect(self, image, target_w, target_h):
        """Referansı EN-BOY oranını koruyarak target kutusuna sığdırır (germe yok)."""
        src_h, src_w = int(image.shape[1]), int(image.shape[2])
        if src_w == 0 or src_h == 0:
            return image
        scale = min(target_w / src_w, target_h / src_h)
        new_w = self._round8(src_w * scale)
        new_h = self._round8(src_h * scale)
        return self._resize_image(image, new_w, new_h)

    def _prepend_trigger(self, trigger, prompt_text):
        trigger = (trigger or "").strip()
        if not trigger:
            return prompt_text
        if not prompt_text:
            return trigger
        return f"{trigger}, {prompt_text}"

    # ---------------- maske işlemleri (GrowMask / FeatherMask kalıbı) ----------------

    @staticmethod
    def _grow_mask(mask, expand, tapered_corners=True):
        """GrowMask (nodes_mask.py): expand>0 dilation, expand<0 erosion."""
        if expand == 0:
            return mask
        c = 0 if tapered_corners else 1
        kernel = np.array([[c, 1, c], [1, 1, 1], [c, 1, c]])
        m = mask.reshape((-1, mask.shape[-2], mask.shape[-1]))
        out = []
        for single in m:
            output = single.cpu().numpy()
            for _ in range(abs(expand)):
                if expand < 0:
                    output = scipy.ndimage.grey_erosion(output, footprint=kernel)
                else:
                    output = scipy.ndimage.grey_dilation(output, footprint=kernel)
            out.append(torch.from_numpy(output))
        return torch.stack(out, dim=0)

    @staticmethod
    def _feather_mask(mask, amount):
        """FeatherMask (nodes_mask.py): tüm kenarlardan eşit gradyan."""
        if amount <= 0:
            return mask
        output = mask.reshape((-1, mask.shape[-2], mask.shape[-1])).clone()
        a = min(amount, output.shape[-1], output.shape[-2])
        for x in range(a):
            rate = (x + 1.0) / a
            output[:, :, x] *= rate
            output[:, :, -(x + 1)] *= rate
        for y in range(a):
            rate = (y + 1.0) / a
            output[:, y, :] *= rate
            output[:, -(y + 1), :] *= rate
        return output

    # ---------------- differential diffusion ----------------

    @staticmethod
    def _apply_differential_diffusion(model):
        """DifferentialDiffusion (nodes_differential_diffusion.py) — maske kenarı yumuşatma."""
        def forward(sigma, denoise_mask, extra_options):
            inner = extra_options["model"]
            step_sigmas = extra_options["sigmas"]
            sigma_to = inner.inner_model.model_sampling.sigma_min
            if step_sigmas[-1] > sigma_to:
                sigma_to = step_sigmas[-1]
            sigma_from = step_sigmas[0]
            ts_from = inner.inner_model.model_sampling.timestep(sigma_from)
            ts_to = inner.inner_model.model_sampling.timestep(sigma_to)
            current_ts = inner.inner_model.model_sampling.timestep(sigma[0])
            threshold = (current_ts - ts_to) / (ts_from - ts_to)
            return (denoise_mask >= threshold).to(denoise_mask.dtype)

        model = model.clone()
        model.set_model_denoise_mask_function(forward)
        return model

    # ---------------- görüntü <-> latent ----------------

    @staticmethod
    def _round8(v):
        return max(8, int(round(float(v) / 8.0)) * 8)

    def _resize_image(self, image, width, height, method="lanczos"):
        if int(image.shape[2]) == width and int(image.shape[1]) == height:
            return image
        s = image.movedim(-1, 1)
        s = comfy.utils.common_upscale(s, width, height, method, "disabled")
        return s.movedim(1, -1)

    def _resize_mask(self, mask, width, height):
        m = mask.reshape((-1, 1, mask.shape[-2], mask.shape[-1]))
        m = torch.nn.functional.interpolate(m, size=(height, width), mode="bilinear")
        return m  # [B,1,H,W]

    # ---------------- inpaint conditioning (InpaintModelConditioning inline) ----------------

    def _inpaint_conditioning(self, positive, negative, vae, pixels, mask, add_noise_mask):
        """
        InpaintModelConditioning (nodes.py) iç mantığı. pixels [1,H,W,3],
        mask [1,1,H,W] (0..1). Maske içini gri yapıp concat_latent üretir;
        positive/negative'e concat_latent_image + concat_mask ekler.
        """
        orig_pixels = pixels
        pixels = orig_pixels.clone()
        m = (1.0 - mask.round()).squeeze(1)  # [1,H,W]
        for i in range(3):
            pixels[:, :, :, i] -= 0.5
            pixels[:, :, :, i] *= m
            pixels[:, :, :, i] += 0.5

        concat_latent = vae.encode(pixels)
        orig_latent = vae.encode(orig_pixels)

        out_latent = {"samples": orig_latent}
        if add_noise_mask:
            out_latent["noise_mask"] = mask

        out_cond = []
        for cond in (positive, negative):
            c = node_helpers.conditioning_set_values(
                cond, {"concat_latent_image": concat_latent, "concat_mask": mask}
            )
            out_cond.append(c)
        return out_cond[0], out_cond[1], out_latent

    # ---------------- composite back (ImageCompositeMasked mantığı) ----------------

    @staticmethod
    def _composite_back(original, result, mask):
        """
        Maske dışını orijinalden birebir koru:
            out = original*(1-mask) + result*mask
        original/result [1,H,W,3], mask [1,1,H,W] (0..1).
        """
        result = result.to(original.device)
        if result.shape[1:3] != original.shape[1:3]:
            result = torch.nn.functional.interpolate(
                result.movedim(-1, 1),
                size=(original.shape[1], original.shape[2]),
                mode="bilinear",
            ).movedim(1, -1)
        m = mask.to(original.device)
        if m.shape[-2:] != original.shape[1:3]:
            m = torch.nn.functional.interpolate(
                m, size=(original.shape[1], original.shape[2]), mode="bilinear"
            )
        m = m.squeeze(1).unsqueeze(-1).clamp(0, 1)  # [1,H,W,1]
        return original * (1.0 - m) + result * m

    # ---------------- diske kaydet (Simple Image Generator kalıbı) ----------------

    @staticmethod
    def _save_image(image, output_subdir, filename_prefix):
        try:
            out_dir = output_subdir or "inpaint_studio"
            if not os.path.isabs(out_dir):
                out_dir = os.path.join(folder_paths.get_output_directory(), out_dir)
            os.makedirs(out_dir, exist_ok=True)
            prefix = filename_prefix or "inpaint"
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

    # ---------------- ana ----------------

    def generate(
        self,
        image,
        prompt,
        trigger_words,
        use_references,
        unet_name,
        vae_name,
        clip_name,
        clip_type,
        lora_name,
        lora_strength,
        denoise,
        grow_mask,
        feather_mask,
        noise_mask,
        differential_diffusion,
        composite_back,
        steps,
        cfg,
        guidance,
        sampler_name,
        scheduler,
        seed,
        seed_mode,
        save_to_disk=False,
        output_subdir="inpaint_studio",
        filename_prefix="inpaint",
        reference_images=None,
        **kwargs,
    ):
        # 1) Resim + maske oku (MaskEditor alpha kanalından).
        src_image, src_mask = self._load_image_and_mask(image)
        in_h, in_w = int(src_image.shape[1]), int(src_image.shape[2])

        # Maske hiç boyanmamış mı? (tamamen 0) -> uyar, orijinali döndür.
        mask_sum = float(src_mask.sum().item())
        if mask_sum <= 1e-6:
            log = (
                f"UYARI: maske boş — resme sağ tıklayıp 'Open in MaskEditor' ile "
                f"değiştirmek istediğin alanı boya. Orijinal görsel döndürüldü. "
                f"({in_w}x{in_h})"
            )
            return {"ui": {"images": []}, "result": (src_image, log)}

        # 2) Çıktı boyutu = yüklenen resmin boyutu (latent için 8'e hizalanır).
        out_w, out_h = self._round8(in_w), self._round8(in_h)
        pixels = self._resize_image(src_image, out_w, out_h)
        mask = self._resize_mask(src_mask, out_w, out_h)  # [1,1,H,W]

        # 3) Maske işleme: grow -> feather (bonuslar).
        mask2d = mask.squeeze(1)  # [1,H,W]
        mask2d = self._grow_mask(mask2d, grow_mask)
        mask2d = self._feather_mask(mask2d, feather_mask)
        mask = mask2d.unsqueeze(1).clamp(0, 1)  # [1,1,H,W]

        # 4) Seed.
        cur_seed = seed if seed_mode == "fixed" else random.randint(0, 0xffffffffffffffff)

        # 5) Model + lora + (opsiyonel) differential diffusion.
        model, vae, clip = self._load_models(unet_name, vae_name, clip_name, clip_type)
        model = self._apply_lora(model, lora_name, lora_strength)
        if differential_diffusion:
            model = self._apply_differential_diffusion(model)

        # 6) Conditioning.
        prompt_text = self._prepend_trigger(trigger_words, prompt)
        positive = self._encode(clip, prompt_text)

        # 6b) Referans görseller (opsiyonel): maske bölgesine eklenecek nesneler
        # Flux2 ReferenceLatent olarak positive'e enjekte edilir. Her referans
        # oran korunarak çıktı boyutuna sığdırılıp VAE encode edilir.
        # NOT: reference_strength sadece referansların eklenip eklenmeyeceğini
        # belirler (0 = kapalı). Latent'i ÇARPMAYIZ — latent uzayında ölçekleme
        # referans görseli bozar; Flux2 referansı ham latent olarak bekler.
        # Referans gücü pratikte guidance + denoise ile ayarlanır.
        ref_count = 0
        ref_latents = []
        if use_references:
            references = self._split_reference_batch(reference_images)
            for ref_img in references:
                fitted = self._fit_keep_aspect(ref_img, out_w, out_h)
                ref_latent = vae.encode(fitted[:, :, :, :3])
                ref_latents.append(ref_latent)
                positive = self._reference_latent(positive, ref_latent)
                ref_count += 1

        positive = self._flux_guidance(positive, guidance)
        negative = self._zero_out(positive)

        # 7) Inpaint conditioning + latent.
        positive, negative, latent = self._inpaint_conditioning(
            positive, negative, vae, pixels, mask, noise_mask
        )

        # 8) Sampling.
        (out_latent,) = nodes.common_ksampler(
            model, cur_seed, steps, cfg, sampler_name, scheduler,
            positive, negative, latent, denoise=denoise,
        )
        result = vae.decode(out_latent["samples"])

        # 9) Composite back (maske dışını koru) — seçilebilir.
        if composite_back:
            # Orijinal (8-hizalı) pikselleri baz al; sonra giriş boyutuna döndür.
            out_image = self._composite_back(pixels, result, mask)
        else:
            out_image = result

        # Giriş çözünürlüğüne geri ölçekle (8-hizalama farkını gizle).
        if (out_image.shape[1], out_image.shape[2]) != (in_h, in_w):
            out_image = self._resize_image(out_image, in_w, in_h)

        ref_label = f" | refs={ref_count}" if ref_count else ""
        log = (
            f"inpaint | {in_w}x{in_h} | denoise={denoise} | grow={grow_mask} "
            f"feather={feather_mask} | diff_diff={differential_diffusion} | "
            f"composite={composite_back}{ref_label} | seed={cur_seed}"
        )

        if save_to_disk:
            saved = self._save_image(out_image, output_subdir, filename_prefix)
            if saved:
                log += f" | saved: {saved}"

        # Bellek temizliği.
        del positive, negative, latent, out_latent
        for rl in ref_latents:
            del rl
        comfy.model_management.soft_empty_cache()

        return {"ui": {"images": []}, "result": (out_image, log)}
