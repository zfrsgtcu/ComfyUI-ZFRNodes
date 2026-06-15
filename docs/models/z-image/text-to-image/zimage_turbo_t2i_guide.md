# Z-Image Turbo Text-to-Image Prompt Guide

## Architecture

Z-Image Turbo is a **distilled model** (Tongyi-MAI). It does not use classifier-free guidance during inference.

**Critical difference:** Negative prompts do not work. The model ignores them.

Strategy: **Addition, not Subtraction.** Describe what you want, not what you don't want.

- Wrong: negative prompt `blurry, bad quality, deformed`
- Right: positive prompt `sharp focus, 8k resolution, highly detailed`

**Key strength:** Accurate text rendering in 20+ languages — better than most other models.

---

## Prompt Structure (4-Layer Formula)

```
[Subject & Action] + [Text in Image] + [Visual Style & Medium] + [Lighting & Atmosphere]
```

### Layer 1: Subject & Action
Be specific. Who, what, doing what.
```
An elderly gardener with wrinkled skin, rough hands, pruning red roses in a Victorian garden.
```

### Layer 2: Text in Image (Z-Image's strength)
Write exact text inside quotes.
```
A rustic wooden sign clearly reads "GARDEN OF LIFE" in elegant font.
```

### Layer 3: Visual Style & Medium
```
Shot on Leica M6, Kodak Portra 400 film grain, cinematic composition.
```
Options: `oil painting`, `watercolor`, `3D render`, `anime illustration`, `shot on [camera model]`

### Layer 4: Lighting & Atmosphere
```
Dappled sunlight filtering through oak trees, soft backlighting, warm morning atmosphere.
```

---

## Settings

| Setting | Value | Notes |
|---|---|---|
| **Steps** | 8 (recommended) | 4 = fast/brainstorm, 8 = quality balance, 12 = sharpest text |
| **Aspect Ratio** | Standard formats | See below |
| **LoRA Weight** | 0.7–0.9 | 1.0 can overcook — stay below |

### Aspect Ratios

| Ratio | Best For |
|---|---|
| 4:3 Landscape | Cinematic scenes, environments |
| 1:1 Square | Avatars, logos, social media |
| 16:9 Portrait | Mobile wallpapers, full-body shots |

---

## No Negative Prompts — Use These Instead

| Instead of negative... | Use positive... |
|---|---|
| `blurry` | `sharp focus, tack sharp` |
| `low quality` | `8k resolution, highly detailed, masterpiece` |
| `bad anatomy` | `perfect anatomy, natural pose` |
| `deformed hands` | `detailed hands, natural fingers` |
| `plastic skin` | `skin texture, pores, imperfections, film grain` |

---

## Text Rendering (Key Feature)

Z-Image is specifically optimized for accurate text in images. Always use quotes:
```
A neon sign reads "OPEN 24/7" in bright red letters.
A newspaper headline reads "BREAKING NEWS" in bold serif font.
```

### Multilingual Text
```
A cyberpunk street at night, neon sign reading "未来世界" (Future World), rain reflection.
```
Works in Chinese, Arabic, Japanese, Korean, and more.

---

## Templates

### Photorealistic Portrait
```
A young woman with curly dark hair, warm smile, standing near a harbor. Shot on Sony A7IV, 85mm f/1.4, natural golden hour light, sharp focus, skin texture, 8k resolution, highly detailed.
```

### Product Photography with Text
```
A premium coffee bag on a marble surface, studio lighting, the label clearly reads "DARK ROAST BLEND" in clean sans-serif font. White background, commercial photography, ultra detailed, sharp shadows.
```

### Cinematic Scene
```
A rainy Tokyo alley at night, neon signs reading "ラーメン" and "OPEN", wet reflections on cobblestones, cinematic anamorphic lens, film grain, moody atmosphere, highly detailed.
```

### Fantasy / Illustration
```
A dragon perched on a mountain peak at sunset, dramatic clouds, epic fantasy art style, detailed scales, rim lighting, painterly texture, vibrant colors, highly detailed.
```

### Social Media / Logo Style
```
Minimalist logo design, a stylized wolf head, clean vector illustration, midnight blue and gold color scheme, white background, professional brand identity, sharp edges, 1:1 square.
```

---

## Common Mistakes

| Mistake | Fix |
|---|---|
| Using negative prompts | Remove them — describe the positive instead |
| Conflicting styles | Don't mix `photorealistic` + `anime` in same prompt |
| Prompt too long | Keep to ~50-60 words max. Most important elements first. |
| Plastic/flat skin | Add `skin texture`, `pores`, `imperfections`, `film grain` |
| Text misspelled | Put exact text in quotes, early in prompt |
| LoRA weight 1.0 | Lower to 0.7–0.9 |

---

## Key Differences vs Other Models

| Feature | Z-Image Turbo | Flux 2 | SDXL | SD 1.5 |
|---|---|---|---|---|
| Negative prompts | **Not supported** | Not supported | Mandatory | Mandatory |
| Text rendering | **Excellent** | Good | Poor | Poor |
| Speed | **Sub-second** | Slow | Medium | Fast |
| Multilingual | **Yes** | Limited | No | No |
| Prompt style | Natural language | Natural language / JSON | Tags + sentences | Keyword tags |
| Steps needed | 4–12 | 20–50 | 30–50 | 20–30 |
