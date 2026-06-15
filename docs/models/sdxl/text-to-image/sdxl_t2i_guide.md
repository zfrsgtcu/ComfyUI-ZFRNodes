# SDXL Text-to-Image Prompt Guide

## Architecture

SDXL uses two text encoders simultaneously (CLIP ViT-L + OpenCLIP ViT-bigG).
- One processes natural language
- One processes keywords and style tags
- Mix both for best results
- Negative prompts are mandatory

---

## Prompt Structure

```
[Subject], [Detailed Description], [Environment], [Mood], [Style], [Quality Tags]
Negative: [unwanted elements]
```

Word order matters — earlier tokens get more attention. Put subject and most important elements first.

---

## Resolution Buckets (strict — do not deviate)

| Resolution | Ratio | Use Case |
|---|---|---|
| 1024×1024 | 1:1 | Square |
| 1152×896 | ~4:3 | Landscape |
| 896×1152 | ~3:4 | Portrait |
| 1216×832 | ~3:2 | Widescreen |
| 1344×768 | 16:9 | Cinematic |
| 1536×640 | ~2.4:1 | Ultra-wide |

---

## Settings

| Setting | Value | Notes |
|---|---|---|
| Steps | 30–50 | 30 speed, 50 max detail |
| CFG Scale | 7.0–8.0 | Below 5 ignores prompt, above 9 burns image |
| Sampler | DPM++ 2M Karras | Gold standard for SDXL |

---

## Techniques

### Attention Weighting
```
(red sports car:1.3) drifting on a racetrack, smoke, motion blur, 8k
Negative: blue car, parked, cartoon
```
Safe range: 0.5–1.5

### BREAK (Concept Isolation)
```
A woman with blue hair BREAK wearing a red dress
```
Prevents concepts from bleeding into each other.

### Danbooru Tags
SDXL recognizes image board tags. Mix with natural language:
```
1girl, long red hair, green eyes, elegant dress, sitting, balcony, neon lights, ultra-detailed
```

### Universal Negative Prompt
```
text, watermark, bad anatomy, blurry, low quality, cropped, deformed hands, extra fingers, missing fingers, worst quality, jpeg artifacts, signature
```

---

## Templates

### Portrait
```
Positive: (portrait of a young woman:1.2), natural light, sharp focus, detailed skin, dslr, Fujifilm XT3, f/1.8, golden hour
Negative: cartoon, painting, anime, blurry, deformed, extra fingers, text, watermark, low quality
```

### Product Photography
```
Positive: (product:1.3) on marble surface, studio lighting, white background, commercial photography, ultra detailed, 8k
Negative: shadow, text, watermark, reflections, blurry, poor quality
```

### Cinematic Scene
```
Positive: rainy Tokyo street at night, neon reflections on wet pavement, cinematic, anamorphic lens, film grain, moody
Negative: cartoon, anime, blur, overexposed, text, watermark
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Cropped / duplicated | Use resolution buckets only |
| Prompt ignored | Use `(element:1.2)` weighting |
| Colors bleeding | Use `BREAK` keyword |
| Burned image | Lower CFG to 7.0–8.0 |
| Bad anatomy | Add anatomy negatives |
