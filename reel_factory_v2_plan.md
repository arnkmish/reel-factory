# Reel Factory v2 — Static Frames + Audio-Aligned Assembly

> **Status:** Planning Document  
> **Date:** July 24, 2026  
> **Author:** Hermes Agent  
> **Replaces:** v1 (Nano Banana Pro + Kling Video + MiniMax TTS)  
> **Key Change:** No video model. Static images + per-scene audio alignment via FFmpeg.

---

## 1. Why This Approach

The previous approach used Kling v3 Pro for image-to-video generation. This was:
- **Expensive**: Each 5-10s clip cost $0.35–$0.70, and a 5-scene reel needed 5 clips ($1.75–$3.50 per reel in video alone)
- **Slow**: Kling clips took 2–10 minutes each, often timed out
- **Unreliable**: Long clips (>10s) frequently timed out at 600s
- **Misaligned**: Video and audio durations didn't match, causing the video to end before the narration

The new approach eliminates the video model entirely:
- **Cost**: ~$0.15–$0.25 per reel (5 images at ~$0.035 each + 5 TTS calls at ~$0.01 each)
- **Speed**: No video generation step, pipeline is 3–4x faster
- **Reliability**: Only image generation (fast, ~15s each) and TTS (fast, ~5s each)
- **Alignment**: Audio drives everything. Each static frame spans exactly its narration duration.

---

## 2. Pipeline Overview

```
Corpus Source → Script Generation → Storyboard → Per-Scene TTS Audio
→ Image Generation (Qwen Image 2) → Image Review → FFmpeg Assembly → Final MP4
```

### Stage Flow

```
Stage 1: Source Selection (from corpus)
Stage 2: Script Generation (Hermes LLM)
Stage 3: Storyboard Generation (Hermes LLM)
Stage 4: Audio Generation (per-scene TTS via MiniMax Speech 2.8 HD)
Stage 5: Image Generation (per-scene via Qwen Image 2)
Stage 6: Image Review (structural + optional VLM)
Stage 7: FFmpeg Assembly (static frames + audio + bg music)
Stage 8: Drive Archival (optional)
Stage 9: Sheets Logging (optional)
```

---

## 3. Model & API Details

### 3.1 Image Generation — Qwen Image 2

- **Endpoint:** `fal-ai/qwen-image-2/text-to-image`
- **Cost:** $0.02/megapixel → ~$0.035 per 1080x1920 image (2.07 MP)
- **Output per $1:** ~28 images at 1080x1920
- **API Parameters:**
  ```json
  {
    "prompt": "detailed visual prompt...",
    "negative_prompt": "low resolution, error, worst quality, deformed",
    "image_size": {"width": 1080, "height": 1920},
    "enable_prompt_expansion": true,
    "enable_safety_checker": true,
    "num_images": 1,
    "output_format": "png",
    "seed": 1001
  }
  ```
- **Output:** `{"images": [{"url": "https://..."}], "seed": 42}`
- **Key differences from Nano Banana Pro:**
  - Uses `image_size: {width, height}` (not `aspect_ratio`)
  - Supports `negative_prompt`
  - Uses `enable_prompt_expansion` (LLM prompt optimization)
  - Much cheaper: $0.035 vs $0.0398 per image

### 3.2 Audio Generation — MiniMax Speech 2.8 HD

- **Endpoint:** `fal-ai/minimax/speech-2.8-hd`
- **Cost:** ~$0.01 per scene (~5–15s of speech)
- **Per-scene TTS:** Each scene gets its own TTS call
- **API Parameters:**
  ```json
  {
    "prompt": "narration text for this scene",
    "output_format": "url",
    "language_boost": "English",
    "voice_setting": {
      "voice_id": "English_expressive_narrator",
      "emotion": "neutral",
      "speed": 1.0,
      "vol": 1.0,
      "pitch": 0,
      "english_normalization": true
    },
    "audio_setting": {
      "sample_rate": 44100,
      "bitrate": 128000,
      "format": "mp3",
      "channel": 1
    }
  }
  ```
- **Output:** `{"audio": {"url": "..."}, "duration_ms": 8230}`
- **Duration is the key output** — it drives the assembly timing

### 3.3 No Video Model

- **Removed:** `fal-ai/kling-video/v3/pro/image-to-video`
- **Removed:** `VideoPipeline` class
- **Removed:** `GeneratedClipAsset` model
- **Removed:** `clips` table in DB
- **Removed:** All video generation, polling, timeout, retry logic

---

## 4. Assembly Strategy — Static Frames + Audio Alignment

### 4.1 Core Concept

Each scene produces:
1. One static image (1080x1920 PNG)
2. One audio narration (MP3, known duration)

The FFmpeg assembly:
1. For each scene: create a video segment = static image displayed for the audio's duration + the narration audio track
2. Concatenate all scene segments + end card
3. Add background music at very low volume (8%) underneath everything

### 4.2 FFmpeg Per-Scene Segment

For each scene (e.g., S01 with 8.2s audio):

```bash
ffmpeg -y \
  -loop 1 \
  -i "image_S01.png" \
  -i "narration_S01.mp3" \
  -c:v libx264 \
  -tune stillimage \
  -pix_fmt yuv420p \
  -r 30 \
  -preset fast \
  -crf 23 \
  -c:a aac \
  -b:a 128k \
  -shortest \
  "scene_S01.mp4"
```

Key flags:
- `-loop 1`: Loop the static image to create a video stream
- `-tune stillimage`: x264 preset for static content (better compression)
- `-shortest`: Cut at audio end (audio is the timing master)

### 4.3 Final Concatenation + Background Music

```bash
# Concatenate all scene segments + end card
ffmpeg -y -f concat -safe 0 -i concat_list.txt \
  -c:v libx264 -pix_fmt yuv420p -r 30 -preset fast -crf 23 \
  -c:a aac -b:a 128k \
  video_with_narration.mp4

# Add background music at 8% volume
ffmpeg -y \
  -i video_with_narration.mp4 \
  -i bg_music.mp3 \
  -filter_complex "[1:a]volume=0.08[bg];[0:a][bg]amix=inputs=2:duration=first:dropout_transition=0[aout]" \
  -map 0:v -map "[aout]" \
  -c:v copy -c:a aac -b:a 128k \
  final_reel.mp4
```

### 4.4 Background Music

- Generated by FFmpeg (no API cost): soft ambient pad using sine waves
- 220Hz (A3) + 330Hz (E4) → gentle meditative tone
- Low-pass filtered at 800Hz, echo for warmth
- Volume at 8% (barely audible, doesn't interfere with narration)

### 4.5 No Text Overlays on Images

- Images are clean — no text burned in
- Text overlays (screen_text per scene) are added by FFmpeg as a separate overlay layer
- This keeps images reusable and avoids text rendering issues in the image model
- The text overlay is a semi-transparent PNG burned on top during assembly

---

## 5. Data Model Changes

### 5.1 Models (models.py)

**Removed:**
- `GeneratedClipAsset` — no longer needed
- `video` section in `models.yaml`

**Modified:**
- `GeneratedAudioAsset` — already has `scene_id` and `duration` (from v5 refactor)

**Unchanged:**
- `GeneratedImageAsset` — same fields, just different endpoint
- `ScriptPackage`, `ScriptScene`, `StoryboardPackage`, `StoryboardScene` — unchanged
- `JobRecord` — `clips` field will be empty list (kept for backward compat)

### 5.2 Database Schema (state_store.py)

**Removed:**
- `clips` table — no longer needed

**Modified:**
- `audio_assets` — already has `scene_id` column (from v5 refactor)

**Migration:**
- `CREATE TABLE IF NOT EXISTS` handles new DBs
- For existing DBs, the `clips` table can remain (harmless, just unused)

### 5.3 Config (models.yaml)

```yaml
image:
  primary:
    endpoint: "fal-ai/qwen-image-2/text-to-image"
    role: "high_quality_vertical_generation"

speech:
  primary:
    endpoint: "fal-ai/minimax/speech-2.8-hd"
    role: "multilingual_narration"

review:
  source_model: "hermes-3-llama-3.1-8b"
  vision_model: "hermes-3-vision"
  final_video_model: "hermes-3-vision"
```

Note: `video` section removed entirely.

---

## 6. Code Changes Required

### 6.1 Files to Modify

| File | Change | Description |
|------|--------|-------------|
| `config/models.yaml` | Modify | Remove `video` section, change image endpoint to `qwen-image-2/text-to-image` |
| `src/reel_factory/fal_gateway.py` | Modify | Change image endpoint default to `qwen-image-2/text-to-image`, use `image_size` instead of `aspect_ratio`, support `negative_prompt` + `enable_prompt_expansion`, remove `generate_video()` method |
| `src/reel_factory/image_pipeline.py` | Modify | Change default endpoint, pass `negative_prompt` + `enable_prompt_expansion` |
| `src/reel_factory/video_pipeline.py` | **Delete** | No longer needed |
| `src/reel_factory/audio_pipeline.py` | No change | Already refactored for per-scene TTS in v5 |
| `src/reel_factory/assembly.py` | Rewrite | New assembly: static frames + audio + concat + bg music (no video clips) |
| `src/reel_factory/workflow.py` | Modify | Remove video generation stage, update assembly call, remove video pipeline init |
| `src/reel_factory/models.py` | Modify | Remove `GeneratedClipAsset` (or keep for compat), update `JobRecord.clips` to optional |
| `src/reel_factory/state_store.py` | Modify | Remove `clips` table creation + `record_clip` method (or keep for compat) |
| `tests/` | Update | Remove video pipeline tests, update assembly tests |

### 6.2 New Assembly Pipeline (assembly.py)

```python
class AssemblyPipeline:
    def assemble(self, images, script, narration, storyboard, output_path=None):
        """
        1. Match images to scenes by scene_id
        2. Match narration to scenes by scene_id
        3. For each scene: create video segment (static image + narration audio)
        4. Optionally burn text overlay
        5. Concatenate all segments + end card
        6. Add background music at 8% volume
        """
```

### 6.3 Simplified Workflow

```python
# Stage 4: Audio Generation (per-scene TTS) — same as v5
# Stage 5: Image Generation (Qwen Image 2) — updated endpoint
# Stage 6: Image Review — same as v5
# Stage 7: Assembly — new static-frame approach (NO video stage)
# Stage 8: Drive Archival — same (optional)
# Stage 9: Sheets Logging — same (optional)
```

---

## 7. Cost Comparison

| Component | v1 (Kling) | v2 (Static Frames) |
|-----------|-----------|-------------------|
| Images (5) | $0.20 (Nano Banana Pro) | $0.18 (Qwen Image 2) |
| Video clips (5) | $1.75–$3.50 | $0.00 (removed) |
| TTS (5 scenes) | $0.05 | $0.05 |
| FFmpeg | $0.00 | $0.00 |
| **Total per reel** | **$2.00–$3.75** | **$0.23** |
| **Time per reel** | 20–40 min | 5–8 min |

**Savings: ~90% cost reduction, ~5x faster.**

---

## 8. Attempt Counting & Review Loops

### 8.1 Image Review

- Max 3 attempts per scene image
- If image review fails (missing image, duplicate URL, wrong dimensions), regenerate
- If all 3 attempts fail for a scene, use best-so-far and flag as fallback
- Review checks (structural):
  - All 5 scenes have images
  - No duplicate image URLs
  - Image dimensions are 1080x1920
  - (Future: VLM-based visual quality review)

### 8.2 No Video Review

- No video review loop (no video generation)
- This removes the most expensive and slowest review/retry cycle

### 8.3 Script Review

- Same as v5: check for duplicate narration, narration length, scene count
- Max 3 attempts, fail-closed

---

## 9. Timeline & Quality Tradeoffs

### 9.1 What We Lose

- No motion/movement in the visuals
- No cinematic camera pans or zooms
- Static feel — like a slideshow with narration

### 9.2 What We Gain

- Perfect audio-video alignment (each frame spans exactly its narration)
- Much lower cost (10x cheaper)
- Much faster (5x)
- Much more reliable (no video model timeouts)
- Cleaner images (no motion artifacts)
- Simpler codebase (no video pipeline)

### 9.3 Mitigations for Static Feel

- Use high-quality, detailed image prompts with strong composition
- Text overlays add visual interest and context
- Background music adds atmosphere
- The narration carries the story — images are supportive, not primary
- Future: can add subtle Ken Burns effect (slow zoom/pan) in FFmpeg for a middle-ground option

### 9.4 Future: Ken Burns Effect (Optional Enhancement)

If the static feel is too pronounced, FFmpeg can add a subtle slow zoom/pan:
```bash
# Slow zoom-in over the segment duration
ffmpeg -y -loop 1 -i image.png -i audio.mp3 \
  -vf "scale=1080:1920,zoompan=z='min(zoom+0.0005,1.1)':d=300:s=1080x1920:fps=30" \
  -c:v libx264 -tune stillimage -pix_fmt yuv420p -r 30 \
  -c:a aac -b:a 128k -shortest output.mp4
```

This is a zero-cost enhancement that can be enabled per scene.

---

## 10. Implementation Plan

### Phase 1: Core Refactor (1–2 hours)

1. Update `config/models.yaml` — remove video, change image endpoint
2. Update `fal_gateway.py` — new image endpoint params, remove `generate_video()`
3. Update `image_pipeline.py` — new endpoint, pass `negative_prompt` + `enable_prompt_expansion`
4. Rewrite `assembly.py` — static frames + audio + concat + bg music
5. Update `workflow.py` — remove video stage, update assembly call
6. Update `models.py` — mark `GeneratedClipAsset` as optional/deprecated
7. Update `state_store.py` — keep `clips` table for compat, stop writing to it
8. Update tests

### Phase 2: Verification (30 min)

1. Run pytest suite — all tests pass
2. Ad-hoc verification script — all structural checks pass
3. Dry run — pipeline executes without API calls

### Phase 3: PoC Run (10 min)

1. Clean state DB + output directory
2. Run `python -m reel_factory.cli run-daily --date 2026-07-24`
3. Verify final_reel.mp4: duration, video, audio, alignment
4. Cost check: should be ~$0.23

### Phase 4: Polish (optional)

1. Add Ken Burns effect option
2. Add text overlay timing (fade in/out)
3. Add crossfade transitions between scenes
4. Add VLM-based image review

---

## 11. File Manifest

```
config/models.yaml                          # Modified
src/reel_factory/fal_gateway.py             # Modified
src/reel_factory/image_pipeline.py           # Modified
src/reel_factory/video_pipeline.py           # Deleted (or kept unused)
src/reel_factory/audio_pipeline.py           # Unchanged (v5 per-scene TTS)
src/reel_factory/assembly.py                 # Rewritten
src/reel_factory/workflow.py                 # Modified
src/reel_factory/models.py                  # Modified
src/reel_factory/state_store.py              # Modified
src/reel_factory/drive.py                    # Unchanged
src/reel_factory/sheets.py                   # Unchanged
tests/                                       # Updated
```

---

## 12. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Qwen Image 2 quality lower than Nano Banana Pro | Medium | Low | Image review loop catches bad images; can switch back to Nano Banana Pro ($0.005 more per image) |
| Static frames feel too boring | Medium | Medium | Ken Burns effect, text overlays, background music mitigate |
| MiniMax TTS quality/availability | Low | Medium | Already proven in v4; can switch to other TTS endpoints |
| FFmpeg assembly issues | Low | High | Well-tested FFmpeg commands; fallback to simple concat |
| Fal.ai balance exhaustion | Medium | High | Budget monitoring; cost is 10x lower now |

---

## 13. Summary

This approach trades cinematic video for:
- 10x cost reduction
- 5x speed improvement
- Perfect audio-video alignment
- Dramatically simpler and more reliable pipeline

The core insight: **for spiritual wisdom short-form content, the narration IS the content. The visuals are supportive context, not the main attraction.** Static frames with strong composition + good narration + subtle background music is a proven format (it's how many successful Instagram Reels and YouTube Shorts already work).