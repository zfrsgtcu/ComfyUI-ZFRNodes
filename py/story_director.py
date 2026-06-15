"""
Story Director — kullanıcının kısa (ve herhangi bir dildeki) bir cümlesini,
Story Frame Generator için tutarlı t2i + i2i prompt zinciri üreten bir LLM'e
verilecek mükemmel system/user prompt'una dönüştürür.

Akış:
    [kısa girdi] -> StoryDirector -> (system_prompt, user_prompt)
                 -> OllamaGenerateV2 -> JSON
                 -> Story Frame Generator

Tasarım hedefi: kullanıcı prompt mühendisliği bilmeden, tek cümleyle
(istediği dilde) tatmin edici ve tutarlı bir görsel hikâye zinciri alsın.
"""


SCENE_MODES = [
    "auto",
    "static_camera",
    "tracking_camera",
    "orbiting_camera",
    "cutscene",
    "storyboard",
]

# Kare sayısı: "auto" + 3..12 arası sabitler.
FRAME_COUNTS = ["auto"] + [str(n) for n in range(3, 13)]


# Story Frame Generator'ün beklediği çıktı şeması (LLM'e gösterilir).
_OUTPUT_SCHEMA = """{
  "title": "...",
  "total_frames": N,
  "scene_type": "...",
  "frames": [
    {"frame": 1, "type": "text_to_image", "prompt": "..."},
    {"frame": 2, "type": "image_to_image", "prompt": "..."}
  ]
}"""


# Sade, odaklı çekirdek kurallar. (Eski 15K karakterlik dev prompt LLM'i
# boğuyordu; bu sürüm kısa ve net — promptlar da kısa/temiz çıkar.)
_CORE_RULES = """RULES

1. Plan the frames
- If the user message lists scenes ("Scene 1: ...", "Scene 2: ..."), make ONE frame per scene, in order. Do not merge, split, or reorder. total_frames = number of scenes.
- Otherwise split the story into the requested number of frames yourself, advancing the action one small step per frame.

2. Frame 1 = text_to_image (set the scene)
- One short, natural English sentence or two. Describe: the subject + what it is doing, the location, and the time of day. State the visual style once (e.g. "cartoon 2D children's book style illustration").
- Keep it simple and concrete. NO lens/mm, NO aperture/f-stop, NO Kelvin, NO hex codes, NO film-jargon. Plain language only.

3. Frames 2+ = image_to_image (edit the previous frame)
- The previous frame is kept automatically. Write ONLY what changes this beat — usually the subject's new pose/action, or a new element entering.
- Keep the SAME location and background; they carry over. Do NOT re-describe or change the setting. Do NOT write "Change the background".
- One or two short sentences. Same plain language, no jargon.

4. Consistency
- Restate the subject the same way every frame so it stays the same individual (see REFERENCE STATUS for how to name it).
- Keep one style for the whole sequence; state it only in Frame 1.

5. Output
- Frame 1 type = "text_to_image"; every later frame type = "image_to_image".
- Put the chosen visual style in "scene_type". Return ONLY the JSON, nothing else."""


class StoryDirector:
    """
    Kısa kullanıcı girdisini, Story Frame Generator için JSON üreten bir LLM'e
    verilecek system + user prompt'una çevirir. Çıktı promptlar her zaman
    İngilizce üretilir (Flux 2 için en doğru), ama kullanıcı girdisi herhangi
    bir dilde olabilir.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "user_input": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "A short sentence is enough — in any language. e.g. 'camouflaged viking statue on a mountain, drone shot, 4 frames'",
                }),
                "frame_count": (FRAME_COUNTS, {"default": "auto"}),
                "scene_mode": (SCENE_MODES, {"default": "auto"}),
                "style": ("STRING", {
                    "multiline": False,
                    "default": "",
                    "placeholder": "Leave empty (LLM chooses) or: anime / noir / realistic / comic ...",
                }),
                # Ollama'ya referans görsel (contact sheet) bağladıysan AÇ.
                # Director bunu göremediği için elle bildirilir; LLM'e "referans
                # var, betimleme yapma, konumsal atıf yap" der. Kapalıysa LLM tüm
                # karakterleri kendisi betimler.
                "has_references": ("BOOLEAN", {"default": False}),
                # Frontend (web/zfrnodes.js) tarafından doldurulan gizli alan:
                # frame_count=N seçilince N adet sahne kutusunun içeriği JSON
                # listesi olarak buraya yazılır, örn. ["kedi uyuyor", "yumak düşer"].
                # frame_count=auto iken kullanılmaz (user_input geçerlidir).
                "scenes": ("STRING", {"default": "[]", "multiline": False}),
            },
            "optional": {
                # Prompt Guide (mode=t2i) çıktısı — Frame 1 / text_to_image için.
                "guide_t2i": ("STRING", {"forceInput": True}),
                # Prompt Guide (mode=i2i) çıktısı — Frame 2+ / image_to_image için.
                "guide_i2i": ("STRING", {"forceInput": True}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("system_prompt", "user_prompt")
    FUNCTION = "build"
    CATEGORY = "zfr-nodes"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    # ---------------- yardımcılar ----------------

    def _frame_directive(self, frame_count):
        if frame_count == "auto":
            return (
                "Frame count: AUTO. If the user named a number (e.g. '4 frames', "
                "'6-frame storyboard'), use exactly that. Otherwise choose 3-6 "
                "based on story complexity (simpler -> 3-4, richer -> 5-6)."
            )
        return (
            f"Frame count: EXACTLY {frame_count}. Set total_frames={frame_count} "
            f"and produce exactly {frame_count} frames, UNLESS the user explicitly "
            f"names a different number in their text (the user's number wins)."
        )

    def _reference_block(self, has_references):
        """
        Referans durumu. has_references'a göre LLM'e NET söyler. Director,
        görselin Ollama'ya bağlı olup olmadığını göremez; bu bayrak elle verilir.
        """
        if not has_references:
            return (
                "REFERENCE STATUS: NONE. No reference image is attached. Describe each "
                "character/object's look yourself in Frame 1, then refer to it the same "
                "way in every later frame. Never mention \"Picture 1\" or any image.\n\n"
            )
        return (
            "REFERENCE STATUS: ATTACHED. A reference image is given showing the story's "
            "character(s)/object(s) side by side, left to right (the 1st figure = Picture 1, "
            "the next = Picture 2, etc.; if only one, it is Picture 1).\n"
            "- For anything shown in it, do NOT describe its looks. Refer to it as \"the cat "
            "in Picture 1\", \"the dog in Picture 2\", etc., and use that SAME wording in "
            "every frame. You only describe its pose/action and where it is in the scene.\n"
            "- Figure out which picture is which from how they look (if the user says 'kedi' "
            "and Picture 1 is a cat, that cat is Picture 1).\n"
            "- For anything NOT in the reference, describe it normally.\n"
            "- The reference only defines how things LOOK — never copy its plain background "
            "or side-by-side layout into the scenes.\n\n"
        )

    @staticmethod
    def _parse_scenes(scenes):
        """
        Gizli 'scenes' JSON alanını sahne listesine çevirir. Her sahne bir dict:
        {"text": "...", "type": "text_to_image"|"image_to_image"|""}.
        Geriye uyumlu: eski düz string listesi de kabul edilir (type boş gelir).
        """
        import json
        if isinstance(scenes, (list, tuple)):
            items = list(scenes)
        else:
            text = (scenes or "").strip()
            if not text:
                return []
            try:
                parsed = json.loads(text)
                items = parsed if isinstance(parsed, list) else [parsed]
            except Exception:
                return []
        out = []
        for it in items:
            if isinstance(it, dict):
                t = str(it.get("text", "")).strip()
                ftype = str(it.get("type", "")).strip()
            else:
                t = str(it).strip()
                ftype = ""
            if ftype not in ("text_to_image", "image_to_image"):
                ftype = ""  # boş = kullanıcı seçmedi -> standart düzen
            out.append({"text": t, "type": ftype})
        return out

    def _story_block(self, frame_count, user_input, scenes):
        """
        User mesajındaki "story seed" bölümünü kurar.
          - frame_count=N ve sahne kutuları doluysa: her sahneyi
            "Scene 1 (text_to_image): ..." olarak listeler. Type'ı kullanıcı
            seçtiyse o kullanılır; seçmediyse standart düzen (1. sahne t2i,
            gerisi i2i) varsayılır.
          - Aksi halde: tek serbest metin (user_input) story seed olarak verilir.
        """
        scene_list = self._parse_scenes(scenes)
        if frame_count != "auto" and any(s["text"] for s in scene_list):
            lines = []
            for i, sc in enumerate(scene_list, 1):
                ftype = sc["type"] or ("text_to_image" if i == 1 else "image_to_image")
                txt = sc["text"] if sc["text"] else "(no direction — you decide this beat)"
                lines.append(f"Scene {i} ({ftype}): {txt}")
            body = "\n".join(lines)
            return (
                "Per-scene directions (each scene = exactly one frame, in order; "
                "may be in any language, output English prompts). The type in "
                "parentheses is REQUIRED for that frame — use it exactly:\n"
                f"{body}\n"
                "Turn EACH scene into the matching frame's prompt, in this exact order, "
                "with the given type. (text_to_image = a full fresh scene description; "
                "image_to_image = only what changes from the previous frame.)"
            )
        return (
            "Story seed (may be in any language; output English prompts only):\n"
            f"{user_input if user_input else '(empty — invent a compelling short visual story)'}"
        )

    def _scene_directive(self, scene_mode):
        if scene_mode == "auto":
            return "Camera: choose what fits the story (counting 'scenes/sahne/frames' is just the frame count, not a request for separate panels)."
        if scene_mode == "storyboard":
            return "Camera: storyboard — each frame is a fresh, fully composed shot of a new beat in the same world."
        if scene_mode == "static_camera":
            return "Camera: STATIC — keep the same location, background, and camera in every frame; only the subject's pose/action changes."
        if scene_mode == "tracking_camera":
            return "Camera: TRACKING — the subject moves and the camera follows; each frame shows a new part of the same world while the subject keeps moving the same direction."
        if scene_mode == "orbiting_camera":
            return "Camera: ORBITING — the subject stays put; each frame views it from a new angle/distance around it."
        return "Camera: CUTSCENE — keep the same composition; only expression/gesture or a new element changes."

    def _style_directive(self, style):
        style = (style or "").strip()
        if not style:
            return "Style: pick one style that fits the story and keep it the same in every frame (state it in Frame 1)."
        return f"Style: '{style}' — use this exact style in every frame (state it in Frame 1)."

    def _guide_block(self, guide_t2i, guide_i2i):
        """
        t2i ve i2i rehberlerini iki ayrı etiketli bölüm olarak ekler:
        Frame 1 -> t2i rehberi, Frame 2+ -> i2i rehberi. LLM karıştırmaz.
        """
        t2i = (guide_t2i or "").strip()
        i2i = (guide_i2i or "").strip()
        if not t2i and not i2i:
            return ""
        parts = [
            "\n\n=== MODEL PROMPTING REFERENCE (authoritative for prompt wording) ===",
            "Apply each guide ONLY to the frame type it belongs to — do not mix them:",
            "  • Use the TEXT-TO-IMAGE guide ONLY for Frame 1 (and every frame in storyboard mode).",
            "  • Use the IMAGE-TO-IMAGE guide ONLY for Frame 2+ (non-storyboard modes).",
        ]
        if t2i:
            parts.append(
                "\n--- TEXT-TO-IMAGE GUIDE (for the text_to_image frame only) ---\n"
                f"{t2i}\n"
                "--- END TEXT-TO-IMAGE GUIDE ---"
            )
        if i2i:
            parts.append(
                "\n--- IMAGE-TO-IMAGE GUIDE (for image_to_image frames only) ---\n"
                f"{i2i}\n"
                "--- END IMAGE-TO-IMAGE GUIDE ---"
            )
        parts.append("=== END MODEL PROMPTING REFERENCE ===")
        return "\n".join(parts)

    # ---------------- ana ----------------

    def build(self, user_input, frame_count, scene_mode, style, has_references=False, scenes="[]", guide_t2i=None, guide_i2i=None):
        user_input = (user_input or "").strip()

        system_prompt = (
            "You turn a short story idea into a sequence of simple image prompts for "
            "Flux 2. Return ONLY valid JSON, nothing else.\n\n"
            "JSON schema:\n"
            f"{_OUTPUT_SCHEMA}\n\n"
            "Basics:\n"
            "- WRITE EVERY PROMPT IN ENGLISH, even if the user writes another language.\n"
            "- Keep prompts SHORT, plain, and concrete — like describing a picture to a "
            "friend. No film jargon, no lens/aperture/Kelvin/hex.\n"
            "- If the user describes the scenes, follow them faithfully. If the idea is "
            "vague, fill in the missing details sensibly and never ask questions.\n\n"

            f"{self._reference_block(has_references)}"
            f"{_CORE_RULES}"
            f"{self._guide_block(guide_t2i, guide_i2i)}"
        )

        # User mesajı: bu işe özgü director ayarları (frame_count, scene_mode,
        # style) + ham story seed. Bunlar system_prompt'ta DEĞİL burada durur,
        # böylece system_prompt sabit/genel kalır (cache-dostu, tutarlı).
        user_prompt = (
            "DIRECTOR SETTINGS (apply strictly):\n"
            f"- {self._frame_directive(frame_count)}\n"
            f"- {self._scene_directive(scene_mode)}\n"
            f"- {self._style_directive(style)}\n\n"
            f"{self._story_block(frame_count, user_input, scenes)}\n\n"
            "Produce the JSON now. Return ONLY the JSON object."
        )

        return (system_prompt, user_prompt)
