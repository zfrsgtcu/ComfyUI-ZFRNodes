"""
Reference Image Loader (Path) — bir KLASÖR yolundaki görselleri otomatik yükler.

Reference Image Loader'dan farkı: tek tek upload yerine, frontend'deki
"Select folder" butonuyla seçilen klasördeki TÜM görselleri sırayla okur.
Frontend (web/zfrnodes.js) klasörü bir carousel'de gösterir (isim, çözünürlük,
otomatik kayma, büyütme, yeni sekmede açma). Görsel verisi /zfr/list-folder ve
/zfr/view-file endpoint'lerinden (py/path_server.py) gelir.

Çıkışlar:
  - images       : klasördeki görseller tek IMAGE batch'i (Dataset Prep'e gider)
  - folder_path  : seçilen klasör yolu (STRING) — Dataset Prep çıktı adlandırması için
  - image_count  : görsel sayısı (INT)

Görseller batch'te farklı boyutlarda olabilir; batch için ilk görselin boyutuna
oran KORUNARAK (transparent letterbox) hizalanır — kırpma/germe yok.
"""

import os

import numpy as np
import torch
from PIL import Image, ImageOps

import comfy.utils
import node_helpers


_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff", ".tif")
_BG = (0xD9, 0xD9, 0xD9)


class ReferenceImageLoaderPath:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                # Frontend "Select folder" butonu bu gizli alanı doldurur.
                "folder_path": ("STRING", {"default": "", "multiline": False}),
                # Görsel sayısını sınırla (0 = tümü). Dataset için faydalı.
                "max_images": ("INT", {"default": 0, "min": 0, "max": 100000}),
            }
        }

    RETURN_TYPES = ("IMAGE", "STRING", "INT")
    RETURN_NAMES = ("images", "folder_path", "image_count")
    FUNCTION = "load"
    CATEGORY = "zfr-nodes"

    # ---------------- yardımcılar ----------------

    @staticmethod
    def _list_files(folder, max_images):
        if not folder or not os.path.isdir(folder):
            return []
        try:
            names = sorted(
                n for n in os.listdir(folder)
                if n.lower().endswith(_IMAGE_EXTS)
                and os.path.isfile(os.path.join(folder, n))
            )
        except Exception:
            return []
        if max_images and max_images > 0:
            names = names[:max_images]
        return [os.path.join(folder, n) for n in names]

    @staticmethod
    def _load_one(path):
        """Tek görseli RGB tensörüne çevirir [1,H,W,3]."""
        img = node_helpers.pillow(Image.open, path)
        img = node_helpers.pillow(ImageOps.exif_transpose, img)
        arr = np.array(img.convert("RGB")).astype(np.float32) / 255.0
        return torch.from_numpy(arr)[None, ]

    @staticmethod
    def _to_rgba(image):
        if int(image.shape[-1]) == 4:
            return image
        alpha = torch.ones(
            (image.shape[0], image.shape[1], image.shape[2], 1), dtype=image.dtype
        )
        return torch.cat([image[..., :3], alpha], dim=-1)

    def _fit_on_transparent(self, image, canvas_w, canvas_h):
        """Oran koruyarak transparent tuvale yerleştirir [1,canvas_h,canvas_w,4]."""
        src_h, src_w = int(image.shape[1]), int(image.shape[2])
        scale = min(canvas_w / src_w, canvas_h / src_h)
        new_w = max(1, int(round(src_w * scale)))
        new_h = max(1, int(round(src_h * scale)))
        if new_w != src_w or new_h != src_h:
            resized = comfy.utils.common_upscale(
                image.movedim(-1, 1), new_w, new_h, "bilinear", "disabled"
            ).movedim(1, -1)
        else:
            resized = image
        resized = self._to_rgba(resized)
        canvas = torch.zeros((1, canvas_h, canvas_w, 4), dtype=resized.dtype)
        ox, oy = (canvas_w - new_w) // 2, (canvas_h - new_h) // 2
        canvas[:, oy:oy + new_h, ox:ox + new_w, :] = resized
        return canvas

    def _batch(self, tensors):
        if len(tensors) == 1:
            return self._to_rgba(tensors[0])
        canvas_w = max(int(t.shape[2]) for t in tensors)
        canvas_h = max(int(t.shape[1]) for t in tensors)
        frames = [self._fit_on_transparent(t, canvas_w, canvas_h) for t in tensors]
        return torch.cat(frames, dim=0)

    # ---------------- ana ----------------

    def load(self, folder_path, max_images=0):
        files = self._list_files(folder_path, max_images)
        tensors = []
        for path in files:
            try:
                tensors.append(self._load_one(path))
            except Exception:
                continue

        if not tensors:
            empty = torch.zeros((1, 64, 64, 3), dtype=torch.float32)
            return (empty, folder_path or "", 0)

        batch = self._batch(tensors)
        return (batch, folder_path or "", len(tensors))

    # ---------------- ComfyUI kancaları ----------------

    @classmethod
    def IS_CHANGED(cls, folder_path, max_images=0):
        # Klasör içeriği (dosya adları + boyutları) değişirse yeniden çalış.
        if not folder_path or not os.path.isdir(folder_path):
            return folder_path or ""
        try:
            sig = []
            for n in sorted(os.listdir(folder_path)):
                if n.lower().endswith(_IMAGE_EXTS):
                    p = os.path.join(folder_path, n)
                    sig.append(f"{n}:{os.path.getmtime(p)}:{os.path.getsize(p)}")
            return "|".join(sig) + f"|max={max_images}"
        except Exception:
            return folder_path
