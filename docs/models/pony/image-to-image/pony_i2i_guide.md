# Pony Diffusion XL Image-to-Image Prompt Guide

## How Pony i2i Works

Same SDXL i2i mechanics — input image encoded to latent, prompt guides transformation, denoise controls preservation. Score and source tags must still be present even in i2i mode.

---

## Key Parameter: Denoise Strength

| Strength | Effect |
|---|---|
| 0.1–0.3 | Subtle style shift, color change |
| 0.4–0.6 | Moderate — style transfer, source style change |
| 0.6–0.8 | Heavy transformation |
| 0.9–1.0 | Near full regeneration |

---

## Settings

| Setting | Value |
|---|---|
| Steps | 25–35 |
| CFG Scale | 6.0–7.5 |
| Denoise Strength | 0.4–0.65 |
| Sampler | DPM++ 2M Karras |
| Clip Skip | 2 |

---

## Prompt Strategy

Score tags and source tags are still required in i2i:
```
score_9, score_8_up, score_7_up, [source_tag], rating_safe, [target description]
```

Describe target state, not input image.

---

## Templates

### Photo to Anime
```
Positive: score_9, score_8_up, score_7_up, source_anime, rating_safe, anime style, beautiful face, soft shading, detailed eyes, vibrant colors
Negative: score_3, score_4, source_real, source_pony, rating_explicit, realistic, photograph, bad anatomy, text
Denoise: 0.6–0.7
```

### Photo to Furry Character
```
Positive: score_9, score_8_up, score_7_up, source_furry, rating_safe, anthropomorphic character, detailed fur, expressive face, same pose as reference
Negative: score_3, score_4, source_real, source_anime, rating_explicit, realistic, bad anatomy, text
Denoise: 0.65–0.75
```

### Style Source Swap (anime to pony)
```
Positive: score_9, score_8_up, score_7_up, source_pony, rating_safe, colorful pony, big eyes, same character, cartoon style
Negative: score_3, score_4, source_anime, source_furry, rating_explicit, realistic, text
Denoise: 0.55–0.65
```

### Color / Palette Change
```
Positive: score_9, score_8_up, score_7_up, [original source tag], rating_safe, [character], [new color palette], same composition
Negative: score_3, score_4, rating_explicit, original colors, text, watermark
Denoise: 0.3–0.45
```

### Background Replacement
```
Positive: score_9, score_8_up, score_7_up, [source tag], rating_safe, same character, [new background description], consistent lighting
Negative: score_3, score_4, rating_explicit, original background, text, watermark
Denoise: 0.5–0.6
```

---

## Universal Negative Prompt

```
score_3, score_4, score_5, worst quality, low quality, bad anatomy, bad hands, text, watermark, signature, blurry
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Score tags missing effect | Always put score tags at very start of prompt |
| Wrong source style | Check source tags in both positive and negative |
| Too similar to input | Increase denoise |
| Character lost | Decrease denoise; describe character more specifically |
| Quality degraded | Check score tags are present; lower CFG slightly |
