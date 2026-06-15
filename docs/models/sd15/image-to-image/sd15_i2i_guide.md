# Stable Diffusion 1.5 Image-to-Image Prompt Guide

## How SD 1.5 i2i Works

Input image is encoded into latent space. Prompt guides the transformation. Denoise strength controls how much the original is preserved. SD 1.5 i2i is very sensitive to strength values — small changes have large effects.

---

## Key Parameter: Denoise Strength

| Strength | Effect |
|---|---|
| 0.1–0.25 | Very subtle — minor color/texture shift |
| 0.3–0.5 | Moderate — style transfer, lighting adjustment |
| 0.5–0.75 | Heavy edit — significant content change |
| 0.75–1.0 | Near-full regeneration |

SD 1.5 is more sensitive than SDXL — start lower and increase gradually.

---

## Settings

| Setting | Value | Notes |
|---|---|---|
| Steps | 20–30 | Same as t2i |
| CFG Scale | 7.0–9.0 | Same as t2i |
| Denoise Strength | 0.3–0.6 | Start conservative |
| Sampler | Euler a or DPM++ 2M Karras | Euler a softer for i2i |
| Clip Skip | 1 or 2 | Match your model's preference |

---

## Prompt Strategy

Describe the desired output state, not the input image.
Include quality boosters even in i2i:
```
masterpiece, best quality, [target description]
```

---

## Templates

### Style Transfer (photo → painting)
```
Positive: masterpiece, best quality, oil painting, by Greg Rutkowski, impressionist, warm colors, brushstrokes
Negative: (worst quality, low quality:1.4), photograph, realistic, digital, text, watermark
Denoise: 0.55–0.65
```

### Lighting Change
```
Positive: masterpiece, best quality, same scene, golden hour lighting, warm sunlight, soft shadows
Negative: (worst quality, low quality:1.4), cold light, blue tones, overcast
Denoise: 0.35–0.45
```

### Anime / Illustration Conversion
```
Positive: masterpiece, best quality, anime style, 1girl, beautiful face, soft shading, by WLOP
Negative: (worst quality, low quality:1.4), realistic, photograph, 3d render, bad anatomy
Denoise: 0.6–0.75
```

### Sketch to Render
```
Positive: masterpiece, best quality, detailed illustration, vibrant colors, professional art, clean lines
Negative: (worst quality, low quality:1.4), sketch, rough, draft, unfinished, text, watermark
Denoise: 0.6–0.7
```

### Background Change
```
Positive: masterpiece, best quality, [subject description], [new background], same subject, natural lighting
Negative: (worst quality, low quality:1.4), different person, text, watermark, blurry
Denoise: 0.5–0.65
```

---

## Universal Negative Prompt

```
(worst quality, low quality:1.4), bad anatomy, bad hands, missing fingers, extra digit, blurry, text, watermark, signature, deformed
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Too similar to input | Increase denoise (0.1 at a time) |
| Too different | Decrease denoise (0.1 at a time) |
| Quality degraded | Add quality boosters to positive; add `worst quality, low quality` to negative |
| Anatomy broken | Add anatomy negatives; decrease denoise slightly |
| Style not applying | Increase denoise to 0.6+ |
| Colors wrong | Be more specific in prompt about target colors |
