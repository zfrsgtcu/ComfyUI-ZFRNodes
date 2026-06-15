# Z-Image Turbo Image-to-Image Prompt Guide

## How Z-Image Turbo i2i Works

Same distilled model architecture — no classifier-free guidance, no negative prompts. Input image provides visual context; prompt describes the target output.

**Negative prompts do not work in i2i either.** Always use positive descriptions only.

---

## Key Parameter: Denoise Strength

| Strength | Effect |
|---|---|
| 0.1–0.3 | Subtle shift — color, texture, lighting adjustment |
| 0.4–0.6 | Moderate — style transfer, mood change |
| 0.6–0.8 | Heavy transformation |
| 0.9–1.0 | Near full regeneration |

Turbo models respond quickly — start conservative and increase gradually.

---

## Settings

| Setting | Value | Notes |
|---|---|---|
| Steps | 8 (recommended) | Same as t2i — 4 for fast, 12 for sharp text |
| Denoise Strength | 0.4–0.65 | Start here |
| LoRA Weight | 0.7–0.9 | Keep below 1.0 |

---

## Prompt Strategy

No negative prompts — describe target state positively:
```
[Target subject/scene description] + [Style] + [Lighting] + [Quality descriptors]
```

Put most important elements first (model attention fades after ~60 words).

---

## No Negative Prompts — Use These Instead

| Goal | Positive Phrasing |
|---|---|
| Sharper output | `sharp focus, tack sharp, 8k resolution` |
| Better quality | `highly detailed, masterpiece, professional` |
| Natural skin | `skin texture, pores, natural imperfections, film grain` |
| Clean style | `clean composition, balanced lighting` |

---

## Templates

### Style Transfer (photo → painting)
```
Oil painting, impressionist style, warm brushstrokes, rich texture, painterly quality, highly detailed, artistic masterpiece.
Denoise: 0.6–0.7
```

### Lighting Change (day → night)
```
Same scene at night, city lights, deep blue sky, neon reflections on wet pavement, cinematic atmosphere, moody lighting, highly detailed.
Denoise: 0.5–0.65
```

### Weather Change (clear → rain)
```
Same scene in heavy rain, wet surfaces, rain drops, grey overcast sky, soft diffused light, dramatic atmosphere, film grain.
Denoise: 0.45–0.6
```

### Season Change (summer → winter)
```
Same scene in winter, snow covered ground, bare trees, cold white sky, frost on surfaces, crisp sharp focus, highly detailed.
Denoise: 0.5–0.6
```

### Cinematic Regrade
```
Cinematic color grade, teal and orange tones, film grain, anamorphic lens flare, shallow depth of field, sharp focus, professional cinematography.
Denoise: 0.35–0.5
```

### Text Overlay / Sign Replacement
```
Same scene, the sign clearly reads "NEW TEXT HERE" in bold clean font, sharp legible text, same lighting and composition, highly detailed.
Denoise: 0.3–0.45
```

### Portrait Enhancement
```
Same person, professional studio portrait, soft box lighting, sharp skin texture with natural pores, 8k resolution, photorealistic, highly detailed.
Denoise: 0.35–0.5
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Too similar to input | Increase denoise strength |
| Too different | Decrease denoise strength |
| Plastic/flat look | Add `skin texture`, `film grain`, `imperfections` |
| Style not applying | Increase denoise to 0.6+ |
| Text wrong in output | Put exact text in quotes early in prompt; use 12 steps |
| Identity lost | Decrease denoise; describe subject more specifically |
| Overcooking with LoRA | Lower LoRA weight to 0.7–0.8 |
