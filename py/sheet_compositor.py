"""
Sheet Compositor — tek tek üretilen karakter/nesne sheet'lerini (gri arka
planlı: #d9d9d9) alıp her birinin bounding box'ını tespit edip crop'layarak
yan yana tek bir temiz contact sheet PNG'sine birleştirir.

Akış:
    [N adet sheet (IMAGE batch)] -> Sheet Compositor -> tek contact sheet (IMAGE)

Mantık:
  1. Her görselde arka plan (#d9d9d9) DIŞINDAKİ pikselleri bul.
  2. Bu piksellerin bounding box'ını hesapla, küçük bir pay ekle, crop et.
  3. Tüm crop'ları ortak bir yüksekliğe oran koruyarak ölçekle.
  4. Hepsini gri (#d9d9d9) bir tuvale yan yana, aralarında boşlukla yerleştir.

Böylece dağınık, ortası boş tekli sheet'ler yerine kompakt ve hizalı tek bir
model sheet elde edilir.
"""

import numpy as np
import torch


# Kaynak sheet'lerin sabit arka plan rengi (Asset Sheet Director ile aynı).
_BG = (0xD9, 0xD9, 0xD9)


class SheetCompositor:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                # Birleştirilecek sheet'ler. IMAGE batch ([N,H,W,C]) — örn.
                # Story Frame Generator'ün frames çıktısı doğrudan bağlanabilir.
                "sheets": ("IMAGE",),
                # Tüm karakterlerin ölçekleneceği ortak yükseklik (px).
                "row_height": ("INT", {"default": 512, "min": 64, "max": 4096, "step": 8}),
                # Karakterler arası ve kenar boşluğu (px).
                "spacing": ("INT", {"default": 24, "min": 0, "max": 512, "step": 1}),
                # Bounding box etrafında bırakılacak pay (oran, 0.04 = %4).
                "padding_pct": ("FLOAT", {"default": 0.04, "min": 0.0, "max": 0.5, "step": 0.01}),
                # Bir pikselin "arka plan değil" sayılması için #d9d9d9'den
                # ne kadar farklı olması gerektiği (0-255). Düşük = hassas.
                "bg_threshold": ("INT", {"default": 16, "min": 0, "max": 128, "step": 1}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("contact_sheet",)
    FUNCTION = "compose"
    CATEGORY = "zfr-nodes"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    # ---------------- yardımcılar ----------------

    @staticmethod
    def _to_uint8(image):
        """[H,W,C] float(0-1) -> [H,W,3] uint8 (alpha varsa düşür)."""
        arr = image.detach().cpu().numpy()
        arr = (arr * 255.0).clip(0, 255).astype(np.uint8)
        return arr[:, :, :3]

    @staticmethod
    def _non_bg_bbox(rgb, threshold):
        """
        #d9d9d9 arka plandan threshold'dan fazla sapan piksellerin bounding
        box'ını (y0, y1, x0, x1) döndürür. Hiç bulamazsa tüm kareyi döndürür.
        """
        bg = np.array(_BG, dtype=np.int16)
        diff = np.abs(rgb.astype(np.int16) - bg).max(axis=2)  # her piksel için maks kanal sapması
        mask = diff > threshold

        ys = np.where(mask.any(axis=1))[0]
        xs = np.where(mask.any(axis=0))[0]
        if ys.size == 0 or xs.size == 0:
            # Boş/tamamen arka plan: tüm kareyi kullan.
            h, w = rgb.shape[:2]
            return 0, h, 0, w
        return int(ys[0]), int(ys[-1]) + 1, int(xs[0]), int(xs[-1]) + 1

    @staticmethod
    def _pad_bbox(y0, y1, x0, x1, h, w, padding_pct):
        """Bounding box'a oransal pay ekler, sınırları kareye kırpar."""
        bh, bw = y1 - y0, x1 - x0
        py = int(round(bh * padding_pct))
        px = int(round(bw * padding_pct))
        return (
            max(0, y0 - py),
            min(h, y1 + py),
            max(0, x0 - px),
            min(w, x1 + px),
        )

    @staticmethod
    def _resize_keep_height(rgb, target_h):
        """rgb'yi (uint8 [H,W,3]) oran koruyarak target_h yüksekliğe ölçekler."""
        src_h, src_w = rgb.shape[:2]
        if src_h == 0 or src_w == 0:
            return rgb
        scale = target_h / src_h
        new_w = max(1, int(round(src_w * scale)))
        # torch interpolate ile yeniden boyutlandır (bilinear).
        t = torch.from_numpy(rgb).float().permute(2, 0, 1).unsqueeze(0)  # [1,3,H,W]
        t = torch.nn.functional.interpolate(
            t, size=(target_h, new_w), mode="bilinear", align_corners=False
        )
        out = t.squeeze(0).permute(1, 2, 0).clamp(0, 255).round().to(torch.uint8).numpy()
        return out

    # ---------------- ana ----------------

    def compose(self, sheets, row_height=512, spacing=24, padding_pct=0.04, bg_threshold=16):
        # sheets: [N,H,W,C] float. Tek tek işle.
        n = int(sheets.shape[0]) if sheets is not None and sheets.ndim == 4 else 0
        if n == 0:
            empty = torch.full((1, 64, 64, 3), _BG[0] / 255.0, dtype=torch.float32)
            return (empty,)

        crops = []
        for i in range(n):
            rgb = self._to_uint8(sheets[i])
            h, w = rgb.shape[:2]
            y0, y1, x0, x1 = self._non_bg_bbox(rgb, bg_threshold)
            y0, y1, x0, x1 = self._pad_bbox(y0, y1, x0, x1, h, w, padding_pct)
            crop = rgb[y0:y1, x0:x1]
            crop = self._resize_keep_height(crop, row_height)
            crops.append(crop)

        # Tuval boyutu: yükseklik = row_height + üst/alt boşluk; genişlik =
        # tüm crop genişlikleri + aralar + kenar boşlukları.
        total_w = spacing + sum(c.shape[1] + spacing for c in crops)
        total_h = row_height + 2 * spacing

        canvas = np.empty((total_h, total_w, 3), dtype=np.uint8)
        canvas[:, :] = np.array(_BG, dtype=np.uint8)

        x = spacing
        y = spacing
        for crop in crops:
            cw = crop.shape[1]
            canvas[y:y + row_height, x:x + cw] = crop
            x += cw + spacing

        # uint8 -> float(0-1) IMAGE tensörü [1,H,W,3].
        out = torch.from_numpy(canvas.astype(np.float32) / 255.0).unsqueeze(0)
        return (out,)
