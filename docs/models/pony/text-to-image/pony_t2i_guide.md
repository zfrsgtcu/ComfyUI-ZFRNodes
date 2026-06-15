# Pony Diffusion XL Text-to-Image Prompt Guide

## What is Pony Diffusion

SDXL fine-tune trained on anime, furry, and cartoon datasets. Uses a score-based quality tagging system that must be present in every prompt.

Primary styles: anime, furry/anthropomorphic, western cartoon, stylized illustration.

---

## Score Tags (mandatory — always at start)

```
score_9, score_8_up, score_7_up
```

| Tag | Quality Level |
|---|---|
| score_9 | Top quality |
| score_8_up | High quality |
| score_7_up | Above average |
| score_6_up | Acceptable |

---

## Source Tags

| Tag | Style |
|---|---|
| source_anime | Anime / manga |
| source_furry | Anthropomorphic / furry |
| source_pony | My Little Pony style |
| source_cartoon | Western cartoon |
| source_real | Photographic |

Use unwanted sources in negative prompt to exclude them.

---

## Rating Tags

| Tag | Level |
|---|---|
| rating_safe | All audiences |
| rating_questionable | Suggestive |
| rating_explicit | Adult only |

Always add `rating_safe` to positive for safe generations.

---

## Prompt Structure

```
score_9, score_8_up, score_7_up, [source_tag], rating_safe, [character], [action], [environment], [style details]
Negative: score_3, score_4, score_5, [unwanted source], rating_explicit, [quality negatives]
```

---

## Settings

| Setting | Value | Notes |
|---|---|---|
| Resolution | 1024×1024 | SDXL bucket system |
| Steps | 25–35 | |
| CFG Scale | 6.0–7.5 | Lower than SD 1.5 |
| Sampler | DPM++ 2M Karras or Euler a | |
| Clip Skip | 2 | Recommended |

---

## Universal Negative Prompt

```
score_3, score_4, score_5, worst quality, low quality, bad anatomy, bad hands, missing fingers, extra digit, text, watermark, signature, blurry, jpeg artifacts
```

---

## Templates

### Anime Character
```
Positive: score_9, score_8_up, score_7_up, source_anime, rating_safe, 1girl, long silver hair, blue eyes, school uniform, cherry blossom background, soft lighting, ultra detailed
Negative: score_3, score_4, score_5, source_furry, source_pony, rating_explicit, bad anatomy, text, watermark, blurry, realistic
```

### Furry / Anthropomorphic
```
Positive: score_9, score_8_up, score_7_up, source_furry, rating_safe, anthropomorphic wolf, medieval armor, forest background, detailed fur, dramatic lighting
Negative: score_3, score_4, score_5, source_anime, source_pony, rating_explicit, bad anatomy, text, watermark
```

### Pony Style
```
Positive: score_9, score_8_up, score_7_up, source_pony, rating_safe, colorful pony, big eyes, magical aura, vibrant colors, cartoon style
Negative: score_3, score_4, source_anime, source_furry, rating_explicit, realistic, bad anatomy, text
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Low quality | Add `score_9, score_8_up, score_7_up` at start |
| Wrong style (furry) | Add `source_furry` to negative |
| Wrong style (anime) | Add `source_anime` to negative |
| Pony aesthetic | Add `source_pony` to negative |
| Adult content | Add `rating_explicit, rating_questionable` to negative + `rating_safe` to positive |
