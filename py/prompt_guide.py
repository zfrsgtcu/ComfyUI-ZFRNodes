import os
import re


# Bu dosyanın bulunduğu yer: <repo>/py/prompt_guide.py
# Dökümanlar:               <repo>/docs/models/<model>/<mode_dir>/*.md
_PY_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_DIR = os.path.dirname(_PY_DIR)
_DOCS_DIR = os.path.join(_REPO_DIR, "docs", "models")

# İşlem türü -> klasör adı eşlemesi.
# UI'da kısa jargon (t2i / i2i) gösterilir; diskte açık isimli klasör kullanılır.
_MODE_DIRS = {
    "t2i": "text-to-image",
    "i2i": "image-to-image",
}


def _list_models():
    """docs/models altındaki model klasörlerini (alfabetik) döndürür."""
    if not os.path.isdir(_DOCS_DIR):
        return []
    models = []
    for name in os.listdir(_DOCS_DIR):
        full = os.path.join(_DOCS_DIR, name)
        if os.path.isdir(full):
            models.append(name)
    models.sort()
    return models


def _strip_jsx(text):
    """
    Markdown içindeki JSX/React bileşen kodlarını ve HTML etiketlerini ayıklar,
    geriye okunabilir prompt-rehberi metni bırakır.

    Hedef: flux2 dosyalarındaki `export const PromptCarousel = (...) => {...}`
    gibi bloklar ve `<Tip>`, `<Columns>` vb. etiketler. Markdown başlıkları,
    tablolar, kod blokları (```...```) ve düz metin korunur.
    """
    # 1) `export const ... => { ... };` bloklarını dengeli süslü parantezle sök.
    out = []
    i = 0
    n = len(text)
    while i < n:
        if text.startswith("export const", i) or text.startswith("export function", i):
            # Fonksiyon gövdesinin başını bul. `=>` sonrasındaki ilk `{` gövdedir;
            # böylece parametre destructuring (`({slides})`) ile karışmaz.
            arrow = text.find("=>", i)
            brace = text.find("{", arrow if arrow != -1 else i)
            if brace == -1:
                # Süslü parantez yoksa satır sonuna kadar at.
                nl = text.find("\n", i)
                i = n if nl == -1 else nl + 1
                continue
            depth = 0
            j = brace
            while j < n:
                ch = text[j]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                j += 1
            # Bloğu takip eden ';' ve boşlukları da yut.
            while j < n and text[j] in " \t;":
                j += 1
            i = j
            continue
        out.append(text[i])
        i += 1
    text = "".join(out)

    # 2) JSX bileşen etiketlerini kaldır (<Tip>, </Columns>, <Frame .../> vb.).
    #    Büyük harfle başlayan bileşenleri ve yaygın HTML etiketlerini temizle.
    text = re.sub(r"</?[A-Za-z][\w.]*(\s[^<>]*?)?/?>", "", text)

    # 3) JSX süslü-ifade kalıntılarını ({...}) tek satırlık olanları temizle.
    text = re.sub(r"^\s*\{[^\n{}]*\}\s*$", "", text, flags=re.MULTILINE)

    # 4) Çoklu boş satırları sadeleştir.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class PromptGuide:
    """
    Görsel oluşturma modelleri için dinamik prompt-rehberi node'u.

    Kullanıcı bir model (Flux, SDXL, Qwen, Z-image ...) ve işlem türü
    (t2i / i2i / both) seçer. Node, ilgili modelin o işlem türüne ait
    docs/models/<model>/<text-to-image|image-to-image>/ klasöründeki tüm
    Markdown rehberlerini okuyup tek bir STRING çıktısında birleştirir.
    "both" seçilirse hem t2i hem i2i rehberi tek çıktıda etiketli olarak verilir.

    Çıktı bir "Show Text" node'una bağlanarak görüntülenebilir veya
    doğrudan bir prompt/LLM input'una beslenebilir.
    """

    @classmethod
    def INPUT_TYPES(cls):
        models = _list_models()
        if not models:
            # Hiç klasör yoksa dropdown boş kalmasın diye placeholder.
            models = ["(no models found)"]
        return {
            "required": {
                "model": (models,),
                # t2i / i2i tekil; "both" seçilirse ikisi de birleştirilip verilir.
                "mode": (["t2i", "i2i", "both"], {"default": "t2i"}),
                "strip_jsx": ("BOOLEAN", {"default": True}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("guide",)
    FUNCTION = "run"
    CATEGORY = "zfr-nodes"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        # Disk'teki .md dosyaları değişebileceği için her çalıştırmada yenile.
        return float("nan")

    def _read_mode(self, model, mode, strip_jsx):
        """
        Tek bir mod (t2i veya i2i) için ilgili klasördeki tüm .md rehberlerini
        okuyup tek metinde birleştirir. Hata olursa açıklayıcı metin döndürür.
        """
        mode_dir = _MODE_DIRS.get(mode)
        if mode_dir is None:
            return f"[Prompt Guide] Invalid mode: {mode}"

        target_dir = os.path.join(_DOCS_DIR, model, mode_dir)
        if not os.path.isdir(target_dir):
            return (
                f"[Prompt Guide] Folder for model '{model}' / mode '{mode}' "
                f"({mode_dir}) not found.\nLooked in: {target_dir}"
            )

        md_files = sorted(
            f for f in os.listdir(target_dir)
            if f.lower().endswith(".md") and os.path.isfile(os.path.join(target_dir, f))
        )
        if not md_files:
            return f"[Prompt Guide] No .md guide found in '{model}/{mode_dir}'."

        sections = []
        for fname in md_files:
            fpath = os.path.join(target_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as fh:
                    content = fh.read()
            except Exception as exc:
                content = f"(could not read: {exc})"
            if strip_jsx:
                content = _strip_jsx(content)
            sections.append(f"# === {fname} ===\n\n{content}".rstrip())

        header = f"# Prompt Guide — {model} ({mode} / {mode_dir})\n"
        body = "\n\n\n".join(sections)
        return f"{header}\n{body}".strip()

    def run(self, model, mode, strip_jsx=True):
        # "both" -> hem text-to-image hem image-to-image rehberini birleştir.
        if mode == "both":
            t2i = self._read_mode(model, "t2i", strip_jsx)
            i2i = self._read_mode(model, "i2i", strip_jsx)
            combined = (
                "########## TEXT-TO-IMAGE GUIDE ##########\n\n"
                f"{t2i}\n\n\n"
                "########## IMAGE-TO-IMAGE GUIDE ##########\n\n"
                f"{i2i}"
            )
            return (combined.strip(),)

        return (self._read_mode(model, mode, strip_jsx),)
