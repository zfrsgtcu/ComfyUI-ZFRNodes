# SDXL Image-to-Image Prompt Guide

## How SDXL i2i Works

The input image is encoded into latent space and used as a starting point. The prompt guides what changes while the denoise strength controls how much the original is preserved.

---

## Key Parameter: Denoise Strength

| Strength | Effect |
|---|---|
| 0.1–0.3 | Subtle changes — color grading, texture, minor style shift |
| 0.4–0.6 | Moderate edit — style transfer, lighting change, object replacement |
| 0.7–0.9 | Major transformation — new style, heavy content change |
| 1.0 | Full regeneration — same as t2i, input image ignored |

**Rule:** Describe what you want the output to look like, not what the input contains.

---

## Settings

| Setting | Value | Notes |
|---|---|---|
| Steps | 30–50 | Same as t2i |
| CFG Scale | 7.0–8.0 | Same as t2i |
| Denoise Strength | 0.4–0.7 | Start here, adjust |
| Sampler | DPM++ 2M Karras | Consistent with t2i |

---

## Prompt Strategy for i2i

Focus your prompt on the **target state**, not the source:
- Wrong: "a photo of a person in original clothes"
- Right: "a person in a red evening dress, elegant, studio lighting"

Be explicit about what should change and what should stay the same.

---

## Templates

### Style Transfer (photo → painting)
```
Positive: oil painting, impressionist style, warm brushstrokes, artistic, detailed
Negative: photograph, realistic, sharp, digital, text, watermark
Denoise: 0.6–0.7
```

### Lighting Change
```
Positive: golden hour lighting, warm tones, sun rays, soft shadows
Negative: cold light, blue tones, overcast, flat lighting
Denoise: 0.4–0.5
```

### Background Replacement
```
Positive: subject in front of [new background description], same subject preserved, professional photography
Negative: text, watermark, blurry, different person
Denoise: 0.5–0.6
```

### Outfit Change
```
Positive: same person wearing [new outfit description], same face and hairstyle, studio lighting
Negative: different face, different hair, text, watermark
Denoise: 0.5–0.7
```

### Season / Weather Change
```
Positive: [scene] in winter, snow covered ground, bare trees, cold atmosphere, overcast sky
Negative: summer, green leaves, warm, sunny
Denoise: 0.5–0.6
```

### Material / Color Change
```
Positive: [object] in [new material or color], same shape and composition, studio lighting
Negative: original color, text, watermark
Denoise: 0.3–0.5
```

---

## Negative Prompt (always include)
```
text, watermark, blurry, low quality, deformed, bad anatomy, extra fingers, signature
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Too similar to input | Increase denoise strength |
| Too different from input | Decrease denoise strength |
| Subject identity lost | Decrease denoise, be more specific about preserving features |
| Style not applying | Increase denoise to 0.6–0.7 |
| Artifacts | Lower CFG, check resolution bucket |
