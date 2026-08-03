# Reel Factory v2

Automated Short-Story Reel Generator — creates vertical (1080x1920) videos
from public-domain spiritual wisdom and moral stories.

## What It Does

1. Selects a story from the corpus (353 manifests: Aesop, Jataka, Panchatantra, Gita, Upanishads, Veda, Indian Fairy Tales)
2. Generates a 5-scene script via Hermes LLM
3. Creates a storyboard with per-scene image prompts
4. Generates per-scene TTS narration (audio drives timing)
5. Generates per-scene images with character consistency (sequential image-to-image editing)
6. Assembles the final video via FFmpeg (static frames + audio alignment + ambient bg music)
7. Optionally archives to Google Drive and logs to Google Sheets

## Setup

1. Install dependencies: `pip install .` (or `uv pip install .`)
2. Configure `.env` using `.env.example` (FAL_KEY required for real runs)
3. Run doctor: `reel-factory doctor`

## PoC Run

```bash
# Dry run (no API calls, no cost):
reel-factory run-daily --date 2026-08-03 --dry-run

# Real run:
reel-factory run-daily --date 2026-08-03

# Force a specific story:
reel-factory run-daily --date 2026-08-03 --source-id aesop-the-hare-and-the-tortoise
```

## Configuration

All config lives in `config/*.yaml`:

- `app.yaml` — general settings, TTS backend/voice/speed, character consistency toggle
- `models.yaml` — fal.ai endpoint definitions (image generation, image editing, TTS backends)
- `review_thresholds.yaml` — quality thresholds and retry policy
- `drive_sheets.yaml` — Google Drive/Sheets integration (optional)
- `visual_styles.yaml` — visual style definitions

### TTS Backends

Three backends are supported, configured via `app.tts.backend`:

| Backend | Endpoint | Cost | Best For |
|---------|----------|------|----------|
| kokoro (default) | fal-ai/kokoro/american-english | $0.02/1k chars | Clear, cheap narration |
| minimax | fal-ai/minimax/speech-2.8-hd | ~$0.015/call | Expressive narration |
| seed | fal-ai/bytedance/seed-speech/tts/v2 | $0.03/1k chars | Warm storyteller voice |

### Character Consistency

When `app.image.character_consistency` is true (default):
- Scene 1 image is generated from scratch via Qwen Image 2
- Scenes 2+ are generated via Qwen Image Edit 2511, editing the previous scene's image
- This preserves character appearance (face, clothes, colors) across all scenes

## Cost

~$0.23 per reel (5 images + 5 TTS calls + FFmpeg assembly).