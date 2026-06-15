import json
import os
import hashlib

import numpy as np
import torch
from PIL import Image, ImageOps

import comfy.utils
import comfy.model_management
import node_helpers
import folder_paths


MAX_IMAGES = 8


class ReferenceImageLoader:
    """
    Tek node içinden 8'e kadar referans görsel yükleyip tek bir IMAGE
    çıkışında (batch) verir.

    Standart LoadImage'dan farkı: IMAGE girişi almaz; görseller node'un
    kendi UI'ından (web/zfrnodes.js'teki "Upload images" butonu) tek tek
    yüklenir. Frontend, yüklenen dosya adlarını JSON listesi olarak gizli
    "images" widget'ına yazar; burada o liste okunup batch'lenir.

    Çıkış "Batch Images" node'uyla aynı mantıkta birleştirilir: tüm
    görseller ilk görselin (w,h) boyutuna ölçeklenip torch.cat ile tek
    batch yapılır.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                # Frontend tarafından doldurulan gizli alan: yüklenen dosya
                # adlarının JSON listesi, örn. ["a.png", "b.jpg"].
                "images": ("STRING", {"default": "[]", "multiline": False}),
                # Çıkış modu — frontend ilgili çıkış slotlarını gizler/gösterir:
                #   batch    -> sadece "batch" (tüm görseller tek tensörde)
                #   separate -> sadece image_1..image_8 (her biri ayrı)
                #   both     -> hem batch hem image_1..image_8
                "output_mode": (["batch", "separate", "both"], {"default": "batch"}),
            }
        }

    # Çıkışlar her zaman tanımlı; frontend seçilen moda göre slotları gizler.
    # Sıra: batch, image_1..image_8, count
    RETURN_TYPES = ("IMAGE",) + ("IMAGE",) * MAX_IMAGES + ("INT",)
    RETURN_NAMES = ("batch",) + tuple(f"image_{i}" for i in range(1, MAX_IMAGES + 1)) + ("count",)
    FUNCTION = "load"
    CATEGORY = "zfr-nodes"

    # ---------------- yardımcılar ----------------

    @classmethod
    def _parse_names(cls, images):
        """Gizli widget değerini dosya adı listesine çevirir."""
        if isinstance(images, (list, tuple)):
            names = list(images)
        else:
            text = (images or "").strip()
            if not text:
                return []
            try:
                parsed = json.loads(text)
                names = parsed if isinstance(parsed, list) else [parsed]
            except Exception:
                # JSON değilse tek dosya adı kabul et.
                names = [text]
        # Boşları at, en fazla MAX_IMAGES.
        names = [str(n) for n in names if str(n).strip()]
        return names[:MAX_IMAGES]

    def _load_one(self, name):
        """Tek bir görseli (input klasöründen) RGB tensörüne çevirir [1,H,W,3]."""
        image_path = folder_paths.get_annotated_filepath(name)
        img = node_helpers.pillow(Image.open, image_path)
        img = node_helpers.pillow(ImageOps.exif_transpose, img)
        rgb = img.convert("RGB")
        arr = np.array(rgb).astype(np.float32) / 255.0
        return torch.from_numpy(arr)[None, ]

    def _batch(self, tensors):
        """
        Farklı boyut/oranlardaki görselleri TEK batch'te birleştirir.

        ComfyUI batch tensörü [B, H, W, C] olduğundan tüm kareler aynı H×W
        olmak zorunda. Deformasyon/kırpma OLMADAN bunu sağlamak için:
          - Tüm görseller arasındaki en büyük W ve H taban (tuval) alınır.
          - Her görsel EN-BOY oranı korunarak bu tuvale sığdırılır.
          - Boş kalan kenarlar TRANSPARENT (alpha=0) ile doldurulur -> RGBA.

        Böylece hiçbir görsel gerilmez/kırpılmaz; küçük olanların etrafı
        şeffaf kalır (PNG benzeri).
        """
        if len(tensors) == 1:
            # Tek görsel: yine de RGBA'ya çevirip tutarlı çıktı ver.
            return self._to_rgba(tensors[0])

        # Ortak tuval: en büyük genişlik ve yükseklik.
        canvas_w = max(int(t.shape[2]) for t in tensors)
        canvas_h = max(int(t.shape[1]) for t in tensors)

        frames = [self._fit_on_transparent(t, canvas_w, canvas_h) for t in tensors]
        return torch.cat(frames, dim=0)

    @staticmethod
    def _to_rgba(image):
        """[B,H,W,3] -> [B,H,W,4] (tam opak alpha ekler)."""
        if int(image.shape[-1]) == 4:
            return image
        alpha = torch.ones(
            (image.shape[0], image.shape[1], image.shape[2], 1),
            dtype=image.dtype,
        )
        return torch.cat([image[..., :3], alpha], dim=-1)

    def _fit_on_transparent(self, image, canvas_w, canvas_h):
        """
        Görseli oran koruyarak canvas_w×canvas_h tuvaline yerleştirir; kalan
        kenarları transparent (alpha=0) bırakır. Sonuç [1, canvas_h, canvas_w, 4].
        """
        src_h, src_w = int(image.shape[1]), int(image.shape[2])

        # Oran koruyarak tuvale sığan en büyük boyut.
        scale = min(canvas_w / src_w, canvas_h / src_h)
        new_w = max(1, int(round(src_w * scale)))
        new_h = max(1, int(round(src_h * scale)))

        if new_w != src_w or new_h != src_h:
            resized = comfy.utils.common_upscale(
                image.movedim(-1, 1), new_w, new_h, "bilinear", "disabled"
            ).movedim(1, -1)
        else:
            resized = image
        resized = self._to_rgba(resized)  # [1, new_h, new_w, 4]

        # Şeffaf tuval (alpha=0) ve görseli merkeze yerleştir.
        canvas = torch.zeros((1, canvas_h, canvas_w, 4), dtype=resized.dtype)
        off_x = (canvas_w - new_w) // 2
        off_y = (canvas_h - new_h) // 2
        canvas[:, off_y:off_y + new_h, off_x:off_x + new_w, :] = resized
        return canvas

    # ---------------- ana ----------------

    @staticmethod
    def _empty():
        """Boş slotlar için 1x64x64 siyah görsel (downstream patlamasın)."""
        return torch.zeros((1, 64, 64, 3), dtype=torch.float32)

    def load(self, images, output_mode="batch"):
        names = self._parse_names(images)

        tensors = []
        for name in names:
            try:
                tensors.append(self._load_one(name))
            except Exception:
                # Tek bir bozuk/eksik dosya tüm node'u düşürmesin.
                continue

        count = len(tensors)

        # Batch çıkışı: hiç görsel yoksa siyah placeholder.
        batch = self._batch(tensors) if tensors else self._empty()

        # Ayrı çıkışlar: image_1..image_8. Yüklenmeyen slotlar siyah placeholder.
        # (output_mode'a bakılmaksızın hepsi doldurulur; frontend gizler.)
        separate = []
        for i in range(MAX_IMAGES):
            separate.append(tensors[i] if i < count else self._empty())

        return (batch, *separate, count)

    # ---------------- ComfyUI kancaları ----------------

    @classmethod
    def IS_CHANGED(cls, images, output_mode="batch"):
        # Yüklenen dosyaların içeriği değişirse yeniden çalış.
        names = cls._parse_names(images)
        m = hashlib.sha256()
        for name in names:
            try:
                path = folder_paths.get_annotated_filepath(name)
                with open(path, "rb") as f:
                    m.update(f.read())
            except Exception:
                m.update(str(name).encode("utf-8"))
        return m.hexdigest()

    @classmethod
    def VALIDATE_INPUTS(cls, images, output_mode="batch"):
        # Boş bırakılabilir (node siyah placeholder döndürür); dolu adlar geçerli olmalı.
        for name in cls._parse_names(images):
            if not folder_paths.exists_annotated_filepath(name):
                return f"Invalid image file: {name}"
        return True
