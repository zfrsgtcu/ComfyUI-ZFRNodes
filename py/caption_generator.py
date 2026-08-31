"""
Caption Generator — LLM destekli dataset caption (etiket) üreticisi.

Bir klasördeki görselleri okur, bir vision-LLM'e (Ollama VEYA OpenAI-uyumlu API)
gönderir ve her görsel için training'e hazır caption üretir. LLM bu node'un
İÇİNDE çalışır — ayrı Ollama node'u bağlamaya gerek yoktur.

Akış:
  folder_path -> görseller (gerçek dosya adlarıyla)
              -> 3'erli gruplar halinde LLM'e gönder (bağlam şişmesin)
              -> her görsel için caption
              -> JSON çıktısı + her görselin yanına <ad>.txt yaz

Sağlayıcılar:
  - ollama            : yerel/uzak Ollama (vision modeli; örn. qwen2.5vl, llava)
  - openai-compatible : /v1/chat/completions (OpenAI, LM Studio, Ollama /v1, vb.)

Çıktı .txt'leri: resim adıyla aynı (cat_01.jpg -> cat_01.txt). output_dir boşsa
resimlerin bulunduğu klasöre yazılır (LoRA trainer'ları image+txt eşler).
"""

import os
import io
import json
import base64
import re

from PIL import Image, ImageOps


_IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff", ".tif")

# Desteklenen LLM sağlayıcıları.
PROVIDERS = ["ollama", "openai", "deepseek", "google", "openrouter", "anthropic"]

# Provider -> (varsayılan base_url, çağrı tipi).
# tip: "ollama" (yerel), "openai" (/v1/chat/completions), "anthropic" (/v1/messages)
PROVIDER_INFO = {
    "ollama":     ("http://127.0.0.1:11434", "ollama"),
    "openai":     ("https://api.openai.com/v1", "openai"),
    "deepseek":   ("https://api.deepseek.com/v1", "openai"),
    "google":     ("https://generativelanguage.googleapis.com/v1beta/openai", "openai"),
    "openrouter": ("https://openrouter.ai/api/v1", "openai"),
    "anthropic":  ("https://api.anthropic.com", "anthropic"),
}

# Kullanıcının istediği varsayılan system prompt.
_DEFAULT_SYSTEM = (
    "You are an expert dataset caption writer for Flux 2 LoRA training.\n"
    "Your task is to analyze each image provided and generate precise, detailed, "
    "training-ready captions that follow Flux 2 prompting conventions.\n"
    "Rules:\n\n"
    "Describe exactly what you see. No assumptions, no additions.\n"
    "Always specify the ethnicity, physical appearance, skin tone, age range, and "
    "clothing of any person visible.\n"
    "Describe the location, environment, architecture, lighting, time of day, and "
    "weather conditions in detail.\n"
    "Use natural, descriptive English. No artistic jargon, no abstract terms.\n"
    "Captions must be specific and factual — avoid vague words like \"beautiful\", "
    "\"stunning\", \"amazing\".\n"
    "Do not mention the image quality, resolution, or camera settings unless clearly visible.\n"
    "Write in a single paragraph per image.\n"
    "Output must be a valid JSON array. No explanations, no extra text outside the JSON.\n\n"
    "Output format:\n\n"
    "[\n\n{\n\n\"image_name\": \"filename.jpg\",\n\n"
    "\"prompt_text\": \"detailed caption here\"\n\n}\n\n]\n\n"
    "Below are the Flux 2 prompting guidelines you must follow:"
)


class CaptionGenerator:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {              

                # --- LLM sağlayıcı ---
                "provider": (PROVIDERS, {"default": "ollama"}),
                # api_key: ollama dışı sağlayıcılarda gereklidir (frontend ollama'da gizler).
                "api_key": ("STRING", {"default": ""}),
                # base_url: provider'a göre otomatik dolar (frontend), düzenlenebilir.
                "base_url": ("STRING", {"default": "http://127.0.0.1:11434"}),
                # Model: ollama'da Refresh butonu doldurur; API'lerde elle yazılır.
                "model": (["(set a model)"], {"default": "(set a model)"}),
                  # --- LLM options ---
                "batch_size": ("INT", {"default": 3, "min": 1, "max": 10}),
                "temperature": ("FLOAT", {"default": 0.4, "min": 0.0, "max": 2.0, "step": 0.05}),
                "top_p": ("FLOAT", {"default": 0.9, "min": 0.0, "max": 1.0, "step": 0.01}),
                "num_ctx": ("INT", {"default": 8192, "min": 512, "max": 131072, "step": 512}),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
                "think": ("BOOLEAN", {"default": False}),
                # --- Promptlar ---
                "system_prompt": ("STRING", {"multiline": True, "default": _DEFAULT_SYSTEM}),
                "user_prompt": ("STRING", {
                    "multiline": True,
                    "default": "Write a training caption for each image. Use the exact image_name given.",
                }),
                # Görsel klasörü: frontend'deki "paste path + Load" alanı bu gizli
                # widget'ı doldurur, carousel görselleri önizler. Görünür widget
                # olarak gösterilmez (UI'da paste alanı vardır).
                "folder_path": ("STRING", {"default": "", "multiline": False}),
                # Görsel sayısını sınırla (0 = tümü).
                "max_images": ("INT", {"default": 0, "min": 0, "max": 100000}),
                # Caption .txt'lerinin yazılacağı klasör. Boş = resim klasörü.
                "write_txt": ("BOOLEAN", {"default": True}),              
                "output_txt_folder": ("STRING", {"default": ""})
            },
        }

    RETURN_TYPES = ("STRING", "STRING", "INT")
    RETURN_NAMES = ("captions_json", "log", "count")
    OUTPUT_NODE = True
    FUNCTION = "run"
    CATEGORY = "zfr-nodes"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    @classmethod
    def VALIDATE_INPUTS(cls, model=None, **kwargs):
        # 'model' combo'su frontend'deki "Refresh models" ile dinamik doldurulur;
        # backend'in eski tek-elemanlı listesi nedeniyle "Value not in list"
        # hatası vermesin diye bu input'un doğrulamasını burada üstleniyoruz
        # (her model adını kabul et).
        return True

    # ---------------- görsel ----------------

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
        return names

    @staticmethod
    def _img_b64(path, max_side=1024):
        """Görseli (gerekirse küçülterek) base64 PNG'ye çevirir."""
        img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
        if max(img.size) > max_side:
            img.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode("ascii")

    # ---------------- JSON ayıklama ----------------

    @staticmethod
    def _extract_json_array(text):
        """LLM çıktısındaki ilk dengeli [ ... ] dizisini ayıklar; yoksa None."""
        if not text:
            return None
        # ``` blokları sıyır.
        m = re.search(r"```[a-zA-Z]*\s*\n?(.*?)```", text, re.DOTALL)
        if m:
            text = m.group(1)
        start = text.find("[")
        if start == -1:
            return None
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "[":
                    depth += 1
                elif ch == "]":
                    depth -= 1
                    if depth == 0:
                        chunk = text[start:i + 1]
                        chunk = re.sub(r",(\s*[}\]])", r"\1", chunk)  # trailing comma
                        try:
                            return json.loads(chunk)
                        except Exception:
                            return None
        return None

    # ---------------- LLM çağrıları ----------------

    def _call_ollama(self, base_url, model, system, prompt, img_b64s,
                     temperature, top_p, num_ctx, seed, think):
        from ollama import Client
        client = Client(host=base_url)
        options = {
            "temperature": float(temperature),
            "top_p": float(top_p),
            "num_ctx": int(num_ctx),
        }
        if seed:
            options["seed"] = int(seed)
        resp = client.generate(
            model=model,
            system=system,
            prompt=prompt,
            images=img_b64s,
            options=options,
            think=bool(think),
            keep_alive="5m",
        )
        # ollama yanıtı dict benzeri: .response / ['response']
        try:
            return resp["response"]
        except Exception:
            return getattr(resp, "response", "") or str(resp)

    def _call_openai(self, base_url, api_key, model, system, prompt, img_b64s,
                     temperature, top_p, seed):
        import requests
        url = base_url.rstrip("/")
        if not url.endswith("/v1"):
            url = url + "/v1"
        url = url + "/chat/completions"

        content = [{"type": "text", "text": prompt}]
        for b in img_b64s:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b}"},
            })
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
            "temperature": float(temperature),
            "top_p": float(top_p),
        }
        if seed:
            body["seed"] = int(seed)
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        r = requests.post(url, json=body, headers=headers, timeout=600)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"]

    def _call_anthropic(self, base_url, api_key, model, system, prompt, img_b64s,
                        temperature, top_p):
        import requests
        url = base_url.rstrip("/") + "/v1/messages"
        content = []
        for b in img_b64s:
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": b},
            })
        content.append({"type": "text", "text": prompt})
        body = {
            "model": model,
            "max_tokens": 4096,
            "system": system,
            "temperature": float(temperature),
            "top_p": float(top_p),
            "messages": [{"role": "user", "content": content}],
        }
        headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key or "",
            "anthropic-version": "2023-06-01",
        }
        r = requests.post(url, json=body, headers=headers, timeout=600)
        r.raise_for_status()
        data = r.json()
        # Anthropic: content -> [{type:text, text:...}]
        parts = data.get("content", [])
        return "".join(p.get("text", "") for p in parts if isinstance(p, dict))

    # ---------------- ana ----------------

    def run(
        self,
        folder_path,      
        provider,
        api_key,
        base_url,
        model,
        batch_size,
        temperature,
        top_p,
        num_ctx,
        seed,
        think,
        system_prompt,
        user_prompt,       
        max_images,
        output_txt_folder,
        write_txt
    ):
        names = self._list_files(folder_path, max_images)
        if not names:
            return ("[]", f"No images found in: {folder_path}", 0)

        model = (model or "").strip()
        if not model or model.startswith("("):
            return ("[]", "Set a model first (Ollama: click 'Refresh models'; API: type a model name).", 0)

        # API sağlayıcıları için key zorunlu.
        call_type = PROVIDER_INFO.get(provider, ("", "openai"))[1]
        if call_type != "ollama" and not (api_key or "").strip():
            return ("[]", f"Provider '{provider}' needs an api_key.", 0)

        system = (system_prompt or "").strip()
        out_dir = output_txt_folder.strip() if output_txt_folder else ""
        if out_dir and not os.path.isabs(out_dir):
            # Göreli ise resim klasörüne göre çöz.
            out_dir = os.path.join(folder_path, out_dir)
        if write_txt:
            target_dir = out_dir or folder_path
            try:
                os.makedirs(target_dir, exist_ok=True)
            except Exception:
                pass

        bs = max(1, int(batch_size))
        all_captions = []
        log_lines = [
            f"Caption Generator: provider={provider}, model={model}, "
            f"{len(names)} image(s), batch={bs}"
        ]

        written = 0
        for start in range(0, len(names), bs):
            group = names[start:start + bs]
            img_b64s = []
            valid_group = []
            for nm in group:
                try:
                    img_b64s.append(self._img_b64(os.path.join(folder_path, nm)))
                    valid_group.append(nm)
                except Exception as exc:
                    log_lines.append(f"  skip {nm}: {exc}")
            if not valid_group:
                continue

            # Bu gruptaki gerçek dosya adlarını LLM'e net bildir.
            names_hint = ", ".join(f'"{n}"' for n in valid_group)
            group_prompt = (
                f"{user_prompt}\n\n"
                f"There are {len(valid_group)} image(s) in this batch. Use EXACTLY "
                f"these image_name values, in order: {names_hint}. "
                f"Return a JSON array with one object per image."
            )

            try:
                if call_type == "ollama":
                    raw = self._call_ollama(
                        base_url, model, system, group_prompt, img_b64s,
                        temperature, top_p, num_ctx, seed, think,
                    )
                elif call_type == "anthropic":
                    raw = self._call_anthropic(
                        base_url, api_key, model, system, group_prompt, img_b64s,
                        temperature, top_p,
                    )
                else:  # openai-compatible (openai/deepseek/google/openrouter)
                    raw = self._call_openai(
                        base_url, api_key, model, system, group_prompt, img_b64s,
                        temperature, top_p, seed,
                    )
            except Exception as exc:
                log_lines.append(f"  [batch {start//bs + 1}] LLM error: {exc}")
                continue

            parsed = self._extract_json_array(raw)
            if not isinstance(parsed, list):
                log_lines.append(f"  [batch {start//bs + 1}] JSON parse failed.")
                continue

            # LLM'in image_name'ine güvenme: SIRAYA göre gerçek dosya adıyla eşle.
            for i, nm in enumerate(valid_group):
                cap = ""
                if i < len(parsed) and isinstance(parsed[i], dict):
                    cap = str(parsed[i].get("prompt_text", "")).strip()
                if not cap:
                    log_lines.append(f"  no caption for {nm}")
                    continue
                all_captions.append({"image_name": nm, "prompt_text": cap})

                # Her resim için ayrı .txt (resim adıyla aynı).
                if write_txt:
                    base = os.path.splitext(nm)[0]
                    txt_path = os.path.join(out_dir or folder_path, base + ".txt")
                    try:
                        with open(txt_path, "w", encoding="utf-8") as fh:
                            fh.write(cap)
                        written += 1
                    except Exception as exc:
                        log_lines.append(f"  txt write failed {nm}: {exc}")

            log_lines.append(
                f"  [batch {start//bs + 1}] {len(valid_group)} image(s) captioned"
            )

        log_lines.append(f"Done: {len(all_captions)} captions, {written} .txt written")
        captions_json = json.dumps(all_captions, ensure_ascii=False, indent=2)
        return (captions_json, "\n".join(log_lines), len(all_captions))
