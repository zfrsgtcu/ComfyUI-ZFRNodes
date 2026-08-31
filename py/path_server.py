"""
ZFRNodes — sunucu tarafı yardımcı endpoint'ler (path tabanlı klasör erişimi).

ComfyUI'nin /view endpoint'i güvenlik için yalnızca input/output/temp klasörlerini
sunar; keyfi bir klasördeki ("D:\\indirilenler\\kediler" gibi) görselleri gösteremez.
Reference Image Loader (Path) ve Dataset Prep node'ları için burada üç endpoint kayıtlı:

  GET  /zfr/browse-folder         -> sunucuda native "klasör seç" penceresi açar (tkinter)
  GET  /zfr/list-folder?path=...  -> o klasördeki görselleri (ad, boyut) JSON listeler
  GET  /zfr/view-file?path=...    -> tek bir görsel dosyasını (sadece o klasör altından) sunar

Güvenlik: list/view yalnızca verilen klasörün İÇİNDEKİ dosyalara izin verir
(commonpath kontrolü), üst dizine (..) çıkışı engeller.
"""

import os

from PIL import Image

try:
    from server import PromptServer
    from aiohttp import web
    _HAS_SERVER = True
except Exception:  # ComfyUI dışı ortam / test
    _HAS_SERVER = False


_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff", ".tif")


def pick_folder_native():
    """
    Sunucu makinesinde NATIVE bir "klasör seç" penceresi açar ve seçilen yolu
    döndürür. (chosen, error) demeti döner — chosen boşsa iptal/hata.

    ComfyUI portable Python'unda tkinter genelde YOKTUR; bu yüzden platforma
    göre sırayla denenir:
      Windows -> PowerShell FolderBrowserDialog (tkinter gerekmez)
      macOS   -> osascript (AppleScript)
      Linux   -> zenity / kdialog
    Son çare olarak tkinter denenir.
    """
    import sys
    import subprocess

    # --- Windows: PowerShell (tkinter'sız, her zaman var) ---
    if sys.platform.startswith("win"):
        # Pencereyi öne getirmek için gizli bir TopMost form'a sahip yapılır.
        ps = (
            "Add-Type -AssemblyName System.Windows.Forms;"
            "$top = New-Object System.Windows.Forms.Form;"
            "$top.TopMost = $true; $top.ShowInTaskbar = $false;"
            "$top.Opacity = 0; $top.Show(); $top.Activate();"
            "$f = New-Object System.Windows.Forms.FolderBrowserDialog;"
            "$f.Description = 'Select image folder';"
            "$f.ShowNewFolderButton = $false;"
            "$null = $f.ShowDialog($top);"
            "$top.Close();"
            "[Console]::Out.Write($f.SelectedPath)"
        )
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-STA", "-Command", ps],
                capture_output=True, text=True, timeout=180,
            )
            path = (res.stdout or "").strip()
            if path and os.path.isdir(path):
                return path, None
            return "", None  # iptal
        except subprocess.TimeoutExpired:
            return "", "folder picker timed out (no selection)"
        except Exception as exc:
            return "", f"powershell picker failed: {exc}"

    # --- macOS: osascript ---
    if sys.platform == "darwin":
        script = 'POSIX path of (choose folder with prompt "Select image folder")'
        try:
            res = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=180,
            )
            path = (res.stdout or "").strip()
            if path and os.path.isdir(path):
                return path, None
            return "", None
        except Exception as exc:
            return "", f"osascript picker failed: {exc}"

    # --- Linux: zenity / kdialog ---
    for cmd in (
        ["zenity", "--file-selection", "--directory", "--title=Select image folder"],
        ["kdialog", "--getexistingdirectory", os.path.expanduser("~")],
    ):
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            path = (res.stdout or "").strip()
            if path and os.path.isdir(path):
                return path, None
        except FileNotFoundError:
            continue
        except Exception:
            continue

    # --- Son çare: tkinter ---
    try:
        import tkinter
        from tkinter import filedialog
        root = tkinter.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        path = filedialog.askdirectory() or ""
        root.destroy()
        if path and os.path.isdir(path):
            return path, None
        return "", None
    except Exception as exc:
        return "", (
            "No folder picker available on the server "
            f"(tkinter missing: {exc}). Paste the folder path manually instead."
        )


def list_images_in_folder(folder):
    """
    Bir klasördeki görsel dosyalarını (alt klasörler hariç) ad'a göre sıralı
    döndürür. Her öğe: {name, width, height}. Hata olursa boş liste.
    """
    out = []
    if not folder or not os.path.isdir(folder):
        return out
    try:
        names = sorted(
            n for n in os.listdir(folder)
            if n.lower().endswith(_IMAGE_EXTS)
            and os.path.isfile(os.path.join(folder, n))
        )
    except Exception:
        return out
    for name in names:
        path = os.path.join(folder, name)
        w = h = 0
        try:
            with Image.open(path) as im:
                w, h = im.size
        except Exception:
            pass
        out.append({"name": name, "width": w, "height": h})
    return out


def _safe_join(folder, name):
    """folder/name'i güvenli birleştirir; sonuç folder DIŞINA çıkıyorsa None."""
    if not folder or not name:
        return None
    if name != os.path.basename(name):  # alt yol / .. engelle
        return None
    folder = os.path.abspath(folder)
    full = os.path.abspath(os.path.join(folder, name))
    try:
        if os.path.commonpath([folder, full]) != folder:
            return None
    except Exception:
        return None
    return full


def _register_routes():
    routes = PromptServer.instance.routes

    @routes.get("/zfr/browse-folder")
    async def zfr_browse_folder(request):
        """
        Sunucuda native klasör seçme penceresi açar, seçilen yolu döndürür.
        Picker BLOKLAYICI olduğundan (pencere açıkken bekler) ayrı bir thread'de
        çalıştırılır; böylece ComfyUI'nin event loop'u donmaz.
        """
        import asyncio
        loop = asyncio.get_event_loop()
        chosen, err = await loop.run_in_executor(None, pick_folder_native)
        return web.json_response({"path": chosen, "error": err})

    @routes.get("/zfr/list-folder")
    async def zfr_list_folder(request):
        """Verilen klasördeki görselleri listeler."""
        folder = request.rel_url.query.get("path", "")
        if not folder or not os.path.isdir(folder):
            return web.json_response({"images": [], "error": "folder not found"})
        return web.json_response({"folder": folder, "images": list_images_in_folder(folder)})

    @routes.get("/zfr/ollama-models")
    async def zfr_ollama_models(request):
        """Verilen Ollama host'undaki mevcut modelleri listeler (Caption Generator)."""
        url = request.rel_url.query.get("url", "http://127.0.0.1:11434")
        try:
            from ollama import Client
            client = Client(host=url)
            data = client.list()
            models = data.get("models", []) if isinstance(data, dict) else getattr(data, "models", [])
            out = []
            for m in models:
                name = None
                if isinstance(m, dict):
                    name = m.get("model") or m.get("name")
                else:
                    name = getattr(m, "model", None) or getattr(m, "name", None)
                if name:
                    out.append(str(name))
            return web.json_response({"models": sorted(set(out))})
        except Exception as exc:
            return web.json_response({"models": [], "error": str(exc)})

    @routes.get("/zfr/view-file")
    async def zfr_view_file(request):
        """Tek bir görseli (sadece verilen klasör altından) sunar."""
        folder = request.rel_url.query.get("path", "")
        name = request.rel_url.query.get("name", "")
        full = _safe_join(folder, name)
        if not full or not os.path.isfile(full):
            return web.Response(status=404)
        # İçeriğe göre basit content-type.
        ext = os.path.splitext(full)[1].lower().lstrip(".")
        ctype = {
            "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
            "webp": "image/webp", "gif": "image/gif", "bmp": "image/bmp",
            "tif": "image/tiff", "tiff": "image/tiff",
        }.get(ext, "application/octet-stream")
        try:
            with open(full, "rb") as fh:
                data = fh.read()
        except Exception:
            return web.Response(status=500)
        return web.Response(body=data, content_type=ctype)


if _HAS_SERVER:
    try:
        _register_routes()
    except Exception:
        # Aynı route iki kez kaydedilirse (reload) sessizce geç.
        pass
