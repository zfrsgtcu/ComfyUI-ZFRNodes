# Stable Diffusion 1.5 Text-to-Image Prompt Guide

## Architecture

SD 1.5 uses a single CLIP ViT-L/14 text encoder. Responds best to comma-separated keyword lists. Word order matters — earlier tokens receive more weight. Negative prompts are critical.

---

## Prompt Structure

```
[Quality Boosters], [Subject], [Detailed Description], [Style], [Lighting], [Camera]
Negative: [anatomy fixes], [quality fixes], [style exclusions]
```

Always lead with quality boosters.

---

## Resolution

- Native: 512×512
- Maximum without issues: 768×768
- Above 768: use HiRes Fix to avoid composition problems

---

## Settings

| Setting | Value | Notes |
|---|---|---|
| Steps | 20–30 | Converges faster than SDXL |
| CFG Scale | 7.0–9.0 | 7.5 classic sweet spot |
| Sampler | Euler a or DPM++ 2M Karras | Euler a = soft, DPM++ = sharp |
| Clip Skip | 1 or 2 | 2 often better with fine-tuned models |

---

## Quality Boosters (always add to positive)

```
masterpiece, best quality, ultra detailed, 8k, highly detailed, sharp focus
```

---

## Universal Negative Prompt

```
(worst quality, low quality:1.4), bad anatomy, bad hands, missing fingers, extra digit, fewer digits, fused fingers, mutated hands, poorly drawn face, asymmetric eyes, deformed, blurry, text, watermark, signature, jpeg artifacts, cropped
```

### Textual Inversion Embeddings (recommended)
- **EasyNegative** — add to negative prompt as a single token
- **ng_deepnegative_v1_75t** — stronger anatomy fixing

---

## Techniques

### Keyword Weighting
```
(beautiful face:1.3), long flowing red hair, (green eyes:1.2)
```
Safe range: 0.5–1.5

### Artist Style References
```
portrait of a woman, by Greg Rutkowski, by Artgerm, dramatic lighting, oil painting
```
Common references: Greg Rutkowski, Artgerm, WLOP, Charlie Bowater, Stanley Artgerm Lau

### Photography Terms
```
portrait, dslr photo, Fujifilm XT3, 85mm lens, f/1.8, shallow depth of field, studio lighting
```

---

## Templates

### Photorealistic Portrait
```
Positive: masterpiece, best quality, 1girl, (portrait:1.2), beautiful face, detailed eyes, long brown hair, white dress, sitting in garden, natural sunlight, shallow depth of field, dslr, Fujifilm XT3, f/1.8, ultra detailed
Negative: (worst quality, low quality:1.4), bad anatomy, bad hands, missing fingers, extra fingers, blurry, text, watermark, deformed face
```

### Landscape
```
Positive: masterpiece, best quality, breathtaking landscape, mountains at sunset, golden hour, dramatic sky, photorealistic, ultra detailed, 8k
Negative: (worst quality, low quality:1.4), blurry, overexposed, text, watermark, people
```

### Fantasy / Digital Art
```
Positive: masterpiece, best quality, fantasy warrior woman, detailed armor, epic lighting, by Greg Rutkowski, intricate details, vibrant colors
Negative: (worst quality, low quality:1.4), bad anatomy, deformed, blurry, text, watermark, ugly
```

### Anime Style
```
Positive: masterpiece, best quality, 1girl, anime style, school uniform, cherry blossoms, soft lighting, highly detailed, by WLOP
Negative: (worst quality, low quality:1.4), realistic, photograph, 3d render, bad anatomy, text, watermark
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Bad hands | Negative: `bad hands, missing fingers, extra digit, fused fingers` |
| Blurry | Negative: `blurry, out of focus` — increase steps to 30 |
| Low quality | Positive: `masterpiece, best quality, ultra detailed` |
| Multiple faces | Add `solo` for anime; be more specific in subject description |
| Composition issues | Use img2img workflow: compose in Anything V4, redraw in target model |
