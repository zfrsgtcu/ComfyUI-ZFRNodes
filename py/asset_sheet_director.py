"""
Asset Sheet Director — kullanıcının kısa isteğinden, hikâyedeki karakter/eşya
("asset") için ön/yan/aksiyon/arka referans sheet'leri üreten bir LLM'e
verilecek system + user prompt'una çevirir.

Akış (Aşama 1):
    [kısa istek] -> AssetSheetDirector -> (system_prompt, user_prompt)
                 -> OllamaGenerateV2 -> JSON (assets[])
                 -> StoryFrameGenerator (her asset: front=t2i, gerisi=i2i)

Üretilen sheet'ler, Aşama 2'de sahne üretiminde REFERANS görsel olarak
kullanılır; böylece her sahnede karakter kimliği sabit kalır, poz prompt'tan
serbestçe belirlenir (i2i poz-donması sorunu ortadan kalkar).

Her asset'in ilk view'ı (front) text_to_image, diğerleri (side/action/back)
image_to_image olarak üretilir. Story Frame Generator her text_to_image
frame'inde yeni zincir başlattığı için çok-asset durumunda her asset kendi
front'undan türer; diğer açılar kimliği koruyarak i2i ile döndürülür.
"""


# Asset türüne göre üretilen 4 açı/poz (belgeleme amaçlı; LLM bunları
# system prompt talimatından uygular):
#   - Karakter: front, side, action, back
#   - Nesne/araç: front, side, three_quarter (çapraz yan), back  (action YOK)
CHARACTER_VIEWS = ["front", "side", "action", "back"]
OBJECT_VIEWS = ["front", "side", "three_quarter", "back"]


_OUTPUT_SCHEMA = """{
  "title": "...",
  "total_frames": N,
  "frames": [
    {"frame": 1, "type": "text_to_image",  "prompt": "..."},
    {"frame": 2, "type": "image_to_image", "prompt": "..."},
    {"frame": 3, "type": "image_to_image", "prompt": "..."},
    {"frame": 4, "type": "image_to_image", "prompt": "..."}
  ]
}"""


_CORE_RULES = """STEP 1 — Detect Assets and Classify Each
Identify the distinct characters and important objects ("assets") the story needs as reusable references.
- If the user explicitly lists assets (e.g. "characters: cat, dog, magic wand"), use exactly those.
- Otherwise infer them from the story. Include every named or implied character and every story-critical object (a weapon, a letter, a vehicle, a mug). Do NOT include background scenery, locations, or generic crowd elements — only reusable subjects.
- Keep it focused: typically 1-4 assets.
For EACH asset decide its kind:
- CHARACTER = a living being or anything with a clear front/back and a body that can pose (person, animal, creature, robot, mascot).
- OBJECT = an inanimate thing or vehicle (mug, sword, car, book, lantern). Objects do NOT pose; never give an object an "action" view.

STEP 2 — Lock Each Asset's Identity (anchor)
For every asset, fix 2-4 concrete identity traits and bake them, word-for-word, into every one of that asset's four prompts so all four views look like the same individual.
- Characters: traits like species, color, markings, clothing (e.g. "orange tabby, white paws, green collar").
- Objects: material + color + shape, AND any text/logo/marking on it as a fixed trait (e.g. "dark navy ceramic mug, yellow \\"ZFRNodes\\" text on the front"). There is no separate anchor field.

STEP 3 — Frame Layout (this is the JSON you output)
Output a FLAT "frames" list. For each asset you emit one frame PER VIEW in the exact order given in DIRECTOR SETTINGS (the view set / count is defined there, not here). Then the next asset's views, and so on.
Frame TYPE rule (critical):
- Each asset's FIRST view is type "text_to_image" — a fresh reference plate.
- That asset's remaining views are type "image_to_image" — each edits the previous frame to re-orient/re-pose the SAME item.
- When a NEW asset begins, its first view is again "text_to_image" (starts a new chain so the next asset is not derived from the previous one).
Number frames sequentially across the whole list (1, 2, 3, ...). total_frames = number of assets x (views per asset).

FIRST view (type=text_to_image) — the full reference plate:
- Single fluent English paragraph, 30-50 words. No field labels.
- Begin by naming the asset and stating its full anchor traits (for objects, including the exact text/logo and where it sits, e.g. "yellow \\"ZFRNodes\\" text centered on the front face").
- Plain, even lighting. Plain seamless light-grey background (#d9d9d9), no scenery, no props, no other assets. The asset is centered, full, facing the viewer directly, occupying most of the frame.
- State the art style as 3-4 concrete properties (e.g. soft watercolor washes, gentle pencil outlines, warm muted palette). Use the SAME style for every asset.
- This is a flat reference plate, NOT a cinematic shot. Do NOT include any camera, lens, mm, aperture/f-stop, focal length, Kelvin/color-temperature, depth of field, or shot-type wording.

REMAINING views (type=image_to_image) — edits that re-orient/re-pose the SAME item:
- Each edits the previous frame. Write ONLY the change for this view (a new angle, or for characters a new pose). Short, 15-30 words, ending with "same plain grey background".
- ALWAYS restate the anchor traits as the identity lock (e.g. "Keep the same dark navy ceramic mug with yellow \\"ZFRNodes\\" text"). Flux 2 drifts color/shape/text across edits without this.
- Do NOT re-describe the background, lighting, art style, or framing — those are inherited. Repeating them causes drift.
How to interpret common view names (apply to whatever views were requested):
- front: facing the viewer directly. side: a clean 90-degree left profile. three-quarter: ~45 degrees between front and side. back: a direct rear view. top: a top-down view. action: a characteristic dynamic pose (CHARACTERS ONLY — never for objects).
- For an ACTION view followed by a non-action view, drop the action pose and return the asset to a neutral pose for that next view.
TEXT/LOGO on objects (critical): treat any text or logo as PAINTED ONTO the 3D surface, not a flat sticker. When the object rotates, the text rotates and curves WITH the surface and may be partly or fully hidden (e.g. invisible from the back). NEVER re-stamp the text flat in the center of a rotated view.

STEP 4 — Prohibitions
- No background scenery, environment, ground details, or other assets in any frame.
- No abstract adjectives (cute, majestic, elegant), no time/atmosphere words.
- NO camera/photography wording anywhere: no lens, mm, aperture/f-stop, focal length, Kelvin/color temperature, depth of field, angle, or shot-type. These are flat reference plates, not cinematic shots.
- In image_to_image frames: do not repeat lighting, art style, or background (they are inherited). No pronouns — name the asset.
- Do not change the anchor traits between views. Do not change the art style between assets.
- Objects never get an "action" view (drop any action view requested for an object, or render it as a neutral angle). Never re-stamp text/logo flat in the center of a rotated view — text follows the surface and may be partly or fully hidden at rotated angles.
- Output English only, regardless of the user's input language.

STEP 5 — Pre-Output Checklist
Is "frames" a flat list? Does each asset contribute exactly the requested views, in the requested order (per DIRECTOR SETTINGS)? Is each asset's FIRST view text_to_image and the rest image_to_image? Do frame numbers run 1..N sequentially and total_frames = assets x (views per asset)? Anchor traits restated verbatim in all of an asset's frames? For objects with text/logo: is the text treated as painted on the surface (follows rotation, partly/fully hidden at rotated angles) and NEVER re-stamped flat in the center of a rotated view? First view has full style + grey background + plain lighting? ZERO camera/lens/mm/aperture/Kelvin/shot-type wording anywhere? i2i frames only state the angle/pose change plus the identity lock (no repeated background/style)? Same art style across all assets? No action view on any object?
If any answer is no, rewrite. Return ONLY the JSON."""


class AssetSheetDirector:
    """
    Kısa kullanıcı isteğini, asset (karakter/eşya) referans sheet'leri üreten
    bir LLM'e verilecek system + user prompt'una çevirir. Çıktı promptlar her
    zaman İngilizce; kullanıcı girdisi herhangi bir dilde olabilir.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "user_input": ("STRING", {
                    "multiline": True,
                    "default": "",
                    "placeholder": "A short sentence is enough — in any language. You can also list them, e.g. 'characters: cat, dog'.",
                }),
                # Asset türü: auto (LLM her asset'i kendi tespit eder) /
                # character (hepsi karakter) / object (hepsi nesne/araç).
                "asset_type": (["auto", "character", "object"], {"default": "auto"}),
                # Üretilecek açılar/pozlar — virgülle ayrılmış, serbest metin.
                # Boş bırakılırsa asset_type'a göre varsayılan kullanılır:
                #   character -> front, side, action, back
                #   object    -> front, side, three-quarter, back
                #   auto      -> her asset kendi tipine göre varsayılanı alır
                "views": ("STRING", {
                    "multiline": False,
                    "default": "",
                    "placeholder": "Empty = default. e.g. front, side, action, back  (comma-separated, any number)",
                }),
                "style": ("STRING", {
                    "multiline": False,
                    "default": "",
                    "placeholder": "Leave empty (LLM chooses) or: anime / noir / realistic / comic book ...",
                }),
            },
            "optional": {
                # Prompt Guide (mode=t2i) çıktısı — front (text_to_image) frame için.
                "guide_t2i": ("STRING", {"forceInput": True}),
                # Prompt Guide (mode=i2i) çıktısı — diğer (image_to_image) frame'ler için.
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

    def _style_directive(self, style):
        style = (style or "").strip()
        if not style:
            return (
                "Style: NOT specified — pick ONE genre-appropriate style for the whole "
                "set and expand it into 3-4 concrete visual properties. Use that exact "
                "style in EVERY sheet of EVERY asset."
            )
        return (
            f"Style: '{style}' — expand into 3-4 concrete visual properties and use the "
            f"SAME style in every sheet of every asset."
        )

    @staticmethod
    def _parse_views(views):
        """Virgülle ayrılmış view metnini temiz listeye çevirir. Boşsa []."""
        if not views:
            return []
        parts = [v.strip() for v in str(views).replace("\n", ",").split(",")]
        return [v for v in parts if v]

    def _type_directive(self, asset_type):
        """Asset türü talimatı: auto / character / object."""
        if asset_type == "character":
            return (
                "Asset kind: CHARACTER (forced). Treat EVERY detected asset as a "
                "character (a being with a body/pose), even objects."
            )
        if asset_type == "object":
            return (
                "Asset kind: OBJECT (forced). Treat EVERY detected asset as an "
                "inanimate object/vehicle. Never give any asset an action pose."
            )
        return (
            "Asset kind: AUTO. Classify EACH asset yourself (CHARACTER = a being "
            "that can pose; OBJECT = an inanimate thing/vehicle). Objects never get "
            "an action pose."
        )

    def _views_directive(self, asset_type, views):
        """
        Üretilecek açıları/pozları belirleyen talimat. Kullanıcı 'views' verirse
        onu AYNEN kullandırır (kaç açı -> o kadar frame). Boşsa asset_type'a göre
        varsayılan (CHARACTER_VIEWS / OBJECT_VIEWS) kullanılır.
        """
        custom = self._parse_views(views)
        if custom:
            n = len(custom)
            order = ", ".join(custom)
            return (
                f"Views (USER-DEFINED): produce exactly these {n} view(s) per asset, "
                f"in this exact order: {order}. The first view is text_to_image (a "
                f"fresh reference plate); every following view is image_to_image that "
                f"re-orients/re-poses the SAME asset. total_frames = number of assets x {n}. "
                f"Interpret each view name sensibly (e.g. 'front' = facing the viewer, "
                f"'side' = 90-degree profile, 'three-quarter' = ~45-degree angle, "
                f"'back' = rear view, 'action' = a characteristic dynamic pose, 'top' = "
                f"top-down). If a view is an action/pose, apply it only to characters."
            )
        # Varsayılan: asset_type'a göre.
        char_v = ", ".join(CHARACTER_VIEWS)
        obj_v = ", ".join(OBJECT_VIEWS).replace("three_quarter", "three-quarter")
        if asset_type == "character":
            return (
                f"Views (default): produce exactly four per asset in this order: "
                f"{char_v}. First = text_to_image, rest = image_to_image. total_frames = assets x 4."
            )
        if asset_type == "object":
            return (
                f"Views (default): produce exactly four per asset in this order: "
                f"{obj_v}. First = text_to_image, rest = image_to_image. total_frames = assets x 4."
            )
        return (
            f"Views (default, per kind): CHARACTERS -> {char_v}; OBJECTS -> {obj_v}. "
            f"Four per asset. First = text_to_image, rest = image_to_image. total_frames = assets x 4."
        )

    def _guide_block(self, guide_t2i, guide_i2i):
        """
        t2i ve i2i rehberlerini, hangisinin NE ZAMAN kullanılacağını net
        belirten iki ayrı etiketli bölüm olarak ekler:
          - TEXT-TO-IMAGE guide  -> front frame
          - IMAGE-TO-IMAGE guide -> side/action/back frame
        """
        t2i = (guide_t2i or "").strip()
        i2i = (guide_i2i or "").strip()
        if not t2i and not i2i:
            return ""

        parts = [
            "\n\n=== MODEL PROMPTING REFERENCE (authoritative for prompt wording) ===",
            "Apply each guide ONLY to the frame type it belongs to — do not mix them:",
            "  • Use the TEXT-TO-IMAGE guide ONLY for each asset's front frame.",
            "  • Use the IMAGE-TO-IMAGE guide ONLY for side/action/back frames.",
        ]
        if t2i:
            parts.append(
                "\n--- TEXT-TO-IMAGE GUIDE (for front frames only) ---\n"
                f"{t2i}\n"
                "--- END TEXT-TO-IMAGE GUIDE ---"
            )
        if i2i:
            parts.append(
                "\n--- IMAGE-TO-IMAGE GUIDE (for side/action/back frames only) ---\n"
                f"{i2i}\n"
                "--- END IMAGE-TO-IMAGE GUIDE ---"
            )
        parts.append("=== END MODEL PROMPTING REFERENCE ===")
        return "\n".join(parts)

    # ---------------- ana ----------------

    def build(self, user_input, asset_type, views, style, guide_t2i=None, guide_i2i=None):
        user_input = (user_input or "").strip()

        system_prompt = (
            "You are an expert character designer and Flux 2 prompt engineer. You read "
            "a user's short story seed and produce REUSABLE REFERENCE SHEETS for each "
            "character and important object in it.\n"
            "For every asset you output a fixed set of views in a single flat 'frames' "
            "list, drawn on a plain background in a consistent style, so they can later "
            "be used as reference images that lock the asset's identity across many "
            "scenes. The kind of each asset and the exact view set are given in the "
            "DIRECTOR SETTINGS below. Each asset's FIRST view is text_to_image (a fresh "
            "reference plate); every following view is image_to_image that re-orients/"
            "re-poses the SAME item, so all views look like one thing, not many. Output "
            "the SAME JSON shape that the Story Frame Generator consumes. Return ONLY "
            "valid JSON, nothing else.\n\n"
            "JSON schema:\n"
            f"{_OUTPUT_SCHEMA}\n\n"
            "STEP 0 — Read & Enrich\n"
            "The user's input may be in ANY language and may be short. Understand the "
            "intent, then WRITE EVERY PROMPT IN ENGLISH (Flux 2 performs best in "
            "English). If details are missing (breed, color, wardrobe, material), INVENT "
            "them decisively like a professional designer and commit to them as the "
            "asset's anchor. If the user specifies details, stay faithful to them.\n\n"
            f"{_CORE_RULES}"
            f"{self._guide_block(guide_t2i, guide_i2i)}"
        )

        # İşe-özel ayarlar (asset türü, açılar, stil) user_prompt'ta durur;
        # system_prompt sabit/genel kalır.
        user_prompt = (
            "DIRECTOR SETTINGS (apply strictly):\n"
            "- Assets: detect every distinct subject the story needs yourself; do not "
            "pad with extras.\n"
            f"- {self._type_directive(asset_type)}\n"
            f"- {self._views_directive(asset_type, views)}\n"
            f"- {self._style_directive(style)}\n\n"
            "Story seed (may be in any language; output English prompts only). If it "
            "names specific characters/objects, use exactly those as assets:\n"
            f"{user_input if user_input else '(empty — invent one or two simple characters)'}\n\n"
            "Produce the asset sheets JSON now. Return ONLY the JSON object."
        )

        return (system_prompt, user_prompt)
