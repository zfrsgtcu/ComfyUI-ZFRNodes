"""
clip_type seçeneklerini ComfyUI'den DİNAMİK olarak sağlar.

Eskiden node'larda elle yazılmış 5 tiplik bir liste (["flux2","flux","sd3",
"sdxl","stable_diffusion"]) vardı; bu hem eksikti (ComfyUI 20+ tip destekler)
hem de hatalıydı ("flux"/"sdxl" geçerli CLIPType değil; bilinmeyen tip sessizce
stable_diffusion'a düşer). Burada ComfyUI'nin kendi CLIPLoader'ının sunduğu tam
liste birebir çekilir; ComfyUI güncellenince yeni tipler de otomatik gelir.
"""


def get_clip_types():
    """ComfyUI'nin CLIPLoader'ındaki tam clip_type listesini döndürür."""
    # 1) Tercih: ComfyUI'nin kendi CLIPLoader INPUT_TYPES'ından çek (birebir
    #    ComfyUI ne gösteriyorsa o).
    try:
        import nodes
        loader = nodes.NODE_CLASS_MAPPINGS.get("CLIPLoader")
        if loader is not None:
            types = loader.INPUT_TYPES()["required"]["type"][0]
            if isinstance(types, (list, tuple)) and types:
                return list(types)
    except Exception:
        pass

    # 2) Yedek: CLIPType enum'undan üret.
    try:
        import comfy.sd
        members = [
            name.lower()
            for name in dir(comfy.sd.CLIPType)
            if name.isupper() and not name.startswith("_")
        ]
        if members:
            return sorted(members)
    except Exception:
        pass

    # 3) Son çare: en azından eski liste çalışsın.
    return ["stable_diffusion", "sd3", "flux2"]


def clip_type_input(default="flux2"):
    """
    INPUT_TYPES içinde kullanılacak (choices, {"default": ...}) demetini döndürür.
    default listede yoksa listenin ilk öğesi seçilir (kırılmayı önler).
    """
    choices = get_clip_types()
    if default not in choices:
        default = choices[0] if choices else "stable_diffusion"
    return (choices, {"default": default})
