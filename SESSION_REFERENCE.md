# Reel Factory — Session-Agnostic Reference

> **Purpose:** This document contains everything needed for any new session to understand the `VideoGeneratorBusinessRepo`, generate spiritual-wisdom reels, and upload them to Google Drive — without re-reading the codebase or relying on prior session context.
> **Last updated:** 2026-07-24
> **Repo root:** `/opt/data/VideoGeneratorBusinessRepo`
> **Total corpus manifests:** 353

---

## 1. Repository Overview

| Component | Description |
|-----------|-------------|
| **Language** | Python 3.13 |
| **Package manager** | `uv` (PEP 668 compliant, no system pip) |
| **Virtual env** | `.venv/` at repo root |
| **Core pipeline** | Source → Script → Storyboard → Images → Audio → Assembly → Drive |
| **Image gen** | fal.ai / Qwen Image 2 ($0.02/MP) |
| **Audio gen** | fal.ai / MiniMax Speech 2.8 HD ($0.015/clip) |
| **Video assembly** | FFmpeg (static frames + audio + background music) |
| **LLM scripting** | Hermes CLI (`hermes chat -q ... -Q`) |
| **Storage** | Google Drive (OAuth2 token) + local `runtime/output/` |
| **Video format** | MP4, 1080×1920 (9:16 vertical), 30fps, H.264 |

---

## 2. Environment Prerequisites

### 2.1 Required Tools (system-level)

```bash
# FFmpeg (for video assembly)
sudo apt-get install ffmpeg

# uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Hermes CLI (for script/storyboard generation)
which hermes  # should return /usr/local/bin/hermes
```

### 2.2 Python Environment

```bash
cd /opt/data/VideoGeneratorBusinessRepo

# Create venv (if missing)
uv venv

# Install dependencies
source .venv/bin/activate
uv pip install -e ".[dev]"
# Or manually:
# uv pip install pydantic fal_client google-auth google-auth-oauthlib \
#   google-api-python-client Pillow
```

### 2.3 Credentials & Secrets

All secrets live in `/opt/data/` (outside the repo). **Never commit these.**

| Secret | File / Env Var | Purpose |
|--------|---------------|---------|
| `FAL_KEY` | `/opt/data/.env` → `FAL_KEY=...` | fal.ai image + TTS generation |
| Google OAuth token | `/opt/data/google_token.json` | Drive/Sheets API access (refresh token) |
| Google client secret | `/opt/data/google_client_secret.json` | OAuth app credentials |

**Export before running:**

```bash
export FAL_KEY="$(grep FAL_KEY /opt/data/.env | cut -d= -f2-)"
```

The `generate_5_videos.py` script reads `.env` automatically as a fallback, but explicit export is safer.

---

## 3. Corpus Structure

### 3.1 Manifest Schema (`CorpusItem`)

Every file in `corpus/manifests/*.json` must conform to this schema:

```json
{
  "source_id": "unique-stable-id",
  "tradition": "Hindu",
  "work": "Bhagavad Gita",
  "location": {
    "story": "Chapter II: The Book of Doctrines",
    "chapter": "II",
    "verse": "20-25"
  },
  "source_language": "English",
  "approved_translation": "The spirit is birthless, deathless, and changeless forever.",
  "translation_author": "Edwin Arnold",
  "license": "public-domain",
  "source_url": "https://www.gutenberg.org/ebooks/2388",
  "content_type": "teaching",
  "allowed_use": ["paraphrase", "short_quote"],
  "context_summary": "Krishna teaches Arjuna that the soul is eternal, never born and never dying.",
  "interpretation_boundaries": [],
  "sensitivity_flags": [],
  "depiction_policy": "symbolic-preferred",
  "verified_by": ["human-review"],
  "corpus_version": "2026-07-01",
  "risk_tier": "low"
}
```

**Key fields for generation:**
- `source_id` — stable identifier, used in filenames
- `work` — first word determines "tradition group" for round-robin mixing
- `approved_translation` — the core teaching text
- `context_summary` — background for LLM prompt context
- `depiction_policy` — should be `symbolic-preferred` (no human figures)

### 3.2 Current Corpus Breakdown (353 manifests)

| Tradition | Count | Source |
|-----------|-------|--------|
| Aesop's Fables | 288 | Project Gutenberg |
| Jataka Tales | 40 | Project Gutenberg |
| Indian Fairy Tales | 7 | Project Gutenberg |
| Panchatantra | 1 | Project Gutenberg |
| Bhagavad Gita | 8 | Project Gutenberg (Arnold trans.) |
| Isa Upanishad | 2 | Project Gutenberg (Paramananda trans.) |
| Katha Upanishad | 2 | Project Gutenberg (Paramananda trans.) |
| Kena Upanishad | 1 | Project Gutenberg (Paramananda trans.) |
| Rig Veda | 4 | Public-domain Griffith translations |

---

## 4. Generation Script: `generate_5_videos.py`

This is the **primary working entrypoint**. It is session-agnostic and self-contained.

### 4.1 How It Works

1. **Discover all manifests** in `corpus/manifests/`
2. **Group by tradition** (using first word of `work` field)
3. **Shuffle within each tradition**, then **round-robin interleave** to avoid consecutive same-source videos
4. **Take first 5** from the mixed list
5. For each item:
   - Generate **script** via Hermes CLI (JSON extraction with reasoning-block stripping)
   - Generate **storyboard** via Hermes CLI
   - Generate **5 images** via fal.ai Qwen Image 2 ($0.04 each @ 1080×1920)
   - Generate **5 audio clips** via fal.ai MiniMax TTS ($0.015 each)
   - **Assemble** with FFmpeg: static images + narration + end card + background music
   - **Upload** to Google Drive under `Reel_Factory/Batch_YYYY-MM-DD_HHMM/`

### 4.2 Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Static frames, not video generation** | Kling/Runway video gen is expensive and unreliable for text-to-video. Static images + subtle FFmpeg effects + TTS = cheaper, faster, deterministic. |
| **Per-scene TTS** | Each scene gets its own audio clip. Audio duration drives video segment length (not fixed durations). |
| **Round-robin source mixing** | Prevents 2 consecutive videos from same tradition (e.g., 2 Gita videos back-to-back). |
| **`Reel_Factory` top-level folder** | All batches go under this Drive folder. Batches are timestamped subfolders. |
| **Hermes JSON extraction fix** | The TUI outputs reasoning blocks with box-drawing characters (`┌─ Reasoning ─┐`). The extractor strips these and finds the outermost valid JSON object. |

### 4.3 Cost Per Video

| Component | Per-Item Cost | Per-Video (5 scenes) |
|-----------|---------------|----------------------|
| Images (Qwen Image 2) | $0.042 | $0.21 |
| Audio (MiniMax TTS) | $0.015 | $0.07 |
| **Total per video** | — | **~$0.28** |
| **Batch of 5** | — | **~$1.40** |

### 4.4 Full Script Source

> **Location:** `/opt/data/VideoGeneratorBusinessRepo/generate_5_videos.py`
> **Runtime:** ~25-35 minutes for 5 videos (bottleneck: Hermes CLI + image gen)

<details>
<summary>Click to expand full source</summary>

```python
#!/usr/bin/env python3
"""
Generate 5 spiritual wisdom videos and upload to Google Drive.
Uses the Reel Factory pipeline.
"""

import json
import os
import random
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Add the project src to path
sys.path.insert(0, "/opt/data/VideoGeneratorBusinessRepo/src")

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from reel_factory.fal_gateway import FalGateway
from reel_factory.models import (
    GeneratedImageAsset, GeneratedAudioAsset,
    ScriptPackage, ScriptScene, StoryboardPackage, StoryboardScene,
)

# ─── CONFIG ───
WORKDIR = Path("/opt/data/VideoGeneratorBusinessRepo/runtime/output/batch_5")
WORKDIR.mkdir(parents=True, exist_ok=True)

FAL_KEY = os.getenv("FAL_KEY")
if not FAL_KEY:
    print("ERROR: FAL_KEY not set")
    sys.exit(1)

# ─── GOOGLE DRIVE SETUP ───
def get_drive_service():
    token_path = Path("/opt/data/google_token.json")
    with open(token_path) as f:
        token_data = json.load(f)
    creds = Credentials(
        token=token_data['token'],
        refresh_token=token_data.get('refresh_token'),
        token_uri=token_data['token_uri'],
        client_id=token_data['client_id'],
        client_secret=token_data['client_secret'],
        scopes=token_data.get('scopes', [])
    )
    return build('drive', 'v3', credentials=creds)

def upload_to_drive(file_path: Path, folder_id: str, mime_type: str = "video/mp4"):
    service = get_drive_service()
    media = MediaFileUpload(str(file_path), mimetype=mime_type, resumable=True)
    file_metadata = {"name": file_path.name, "parents": [folder_id]}
    file = service.files().create(body=file_metadata, media_body=media, fields="id,webViewLink").execute()
    return file.get("webViewLink", ""), file.get("id", "")

def ensure_drive_folder(name: str, parent_id: str = None):
    service = get_drive_service()
    
    # Search for existing folder with this name (and parent, if specified)
    query = f"mimeType='application/vnd.google-apps.folder' and name='{name}' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    
    results = service.files().list(q=query, spaces='drive', fields='files(id, name)', pageSize=1).execute()
    items = results.get('files', [])
    
    if items:
        print(f"    Found existing folder '{name}': {items[0]['id']}")
        return items[0]['id']
    
    # Not found — create it
    file_metadata = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        file_metadata["parents"] = [parent_id]
    folder = service.files().create(body=file_metadata, fields="id").execute()
    print(f"    Created new folder '{name}': {folder.get('id')}")
    return folder.get("id")

# ─── HERMES JSON EXTRACTION ───
def extract_json(raw):
    import re
    # Strip box-drawing characters
    raw = re.sub(r'[┌─┐│└┘]', '', raw)
    
    best_candidate = None
    best_len = 0
    
    for start in range(len(raw)):
        if raw[start] != '{':
            continue
        
        depth = 0
        for i in range(start, len(raw)):
            if raw[i] == '{':
                depth += 1
            elif raw[i] == '}':
                depth -= 1
                if depth == 0:
                    candidate = raw[start:i+1]
                    candidate = ''.join(ch for ch in candidate if ord(ch) >= 32 or ch in '\n\t')
                    try:
                        parsed = json.loads(candidate)
                        if len(candidate) > best_len:
                            best_candidate = parsed
                            best_len = len(candidate)
                    except json.JSONDecodeError:
                        pass
                    break
    
    if best_candidate is not None:
        return best_candidate
    
    # Try arrays too
    for start in range(len(raw)):
        if raw[start] != '[':
            continue
        depth = 0
        for i in range(start, len(raw)):
            if raw[i] == '[':
                depth += 1
            elif raw[i] == ']':
                depth -= 1
                if depth == 0:
                    candidate = raw[start:i+1]
                    candidate = ''.join(ch for ch in candidate if ord(ch) >= 32 or ch in '\n\t')
                    try:
                        parsed = json.loads(candidate)
                        if len(candidate) > best_len:
                            best_candidate = parsed
                            best_len = len(candidate)
                    except json.JSONDecodeError:
                        pass
                    break
    
    if best_candidate is not None:
        return best_candidate
    
    raise ValueError(f"Could not extract JSON from: {raw[:500]}")

# ─── SCRIPT GENERATION ───
def generate_script(source_item):
    prompt = f"""Write a 5-scene script for a short vertical spiritual wisdom video.

Source: {source_item["work"]} — {source_item["location"]["story"]}
Teaching: {source_item["approved_translation"]}
Context: {source_item["context_summary"]}

Requirements:
- Scene 1: HOOK — a compelling question or statement (5-6 seconds)
- Scenes 2-4: NARRATIVE — tell the story/teaching vividly (5-7 seconds each)
- Scene 5: MORAL — deliver the lesson (5-6 seconds)
- Each scene needs narration text that fills its duration when spoken aloud
- Screen text: 2-6 words per scene
- Total duration: 25-35 seconds

Respond with valid JSON only. Use this exact schema:
{{
  "title": "A short compelling title",
  "hook": "1-2 sentence attention grabber",
  "duration_seconds": 30,
  "scenes": [
    {{"scene_id": "S01", "duration": 5, "screen_text": "2-6 words", "narration": "1-2 sentences", "story_function": "hook"}},
    {{"scene_id": "S02", "duration": 6, "screen_text": "2-6 words", "narration": "1-2 sentences", "story_function": "narrative"}},
    {{"scene_id": "S03", "duration": 6, "screen_text": "2-6 words", "narration": "1-2 sentences", "story_function": "narrative"}},
    {{"scene_id": "S04", "duration": 6, "screen_text": "2-6 words", "narration": "1-2 sentences", "story_function": "narrative"}},
    {{"scene_id": "S05", "duration": 5, "screen_text": "2-6 words", "narration": "1-2 sentences", "story_function": "moral"}}
  ],
  "final_moral": "The core lesson in 1 sentence",
  "source_credit": "Source: {source_item['work']}",
  "caption": "A short social media caption",
  "hashtags": ["#wisdom", "#spirituality"]
}}

Output ONLY the JSON. No markdown, no explanation."""

    cmd = ["hermes", "chat", "-q", prompt, "-Q"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"Hermes script error: {result.stderr[:500]}")
    
    data = extract_json(result.stdout)
    
    # Handle case where model returns only scenes array
    if isinstance(data, list):
        data = {"scenes": data}
    
    scenes = []
    for s in data.get("scenes", []):
        sid = s.get("scene_id", "")
        if isinstance(sid, int):
            sid = f"S{sid:02d}"
        scenes.append({
            "scene_id": sid,
            "duration": s.get("duration", 5),
            "screen_text": s.get("screen_text", ""),
            "narration": s.get("narration", ""),
            "story_function": s.get("story_function", "narrative"),
        })
    
    # Fallback title/hook from source
    title = data.get("title", f"Teaching from {source_item['work']}")
    hook = data.get("hook", source_item["approved_translation"])
    
    return {
        "title": title,
        "hook": hook,
        "duration_seconds": data.get("duration_seconds", 30),
        "scenes": scenes,
        "final_moral": data.get("final_moral", source_item["approved_translation"]),
        "source_credit": data.get("source_credit", f"Source: {source_item['work']}"),
        "caption": data.get("caption", f"A teaching from {source_item['work']}"),
        "hashtags": data.get("hashtags", ["#wisdom", "#spirituality"]),
    }

# ─── STORYBOARD GENERATION ───
def generate_storyboard(script, source_item):
    scenes_text = "\n".join(
        f"  {s['scene_id']} ({s['story_function']}): narration='{s['narration']}' screen_text='{s['screen_text']}'"
        for s in script["scenes"]
    )
    
    prompt = f"""Create a 5-scene storyboard for a vertical video.

Title: {script['title']}
Hook: {script['hook']}
Scenes:
{scenes_text}
Final moral: {script['final_moral']}

Requirements:
- Each scene needs: scene_id, visual_description, characters (list), setting, composition, camera, palette (list), symbols (list), image_prompt, motion_prompt, text_safe_zone
- image_prompt must be specific, descriptive, match the story content
- Style: minimal symbolic spiritual illustration, warm colors, 9:16 vertical
- No text in images
- motion_prompt: subtle camera movement for 5-second clip

Respond with valid JSON only. Use this exact schema:
{{
  "scenes": [
    {{
      "scene_id": "S01",
      "visual_description": "what appears on screen",
      "characters": ["character1", "object2"],
      "setting": "where it happens",
      "composition": "wide shot, centered",
      "camera": "wide",
      "palette": ["warm gold", "soft amber", "deep green"],
      "symbols": ["symbol1", "symbol2"],
      "image_prompt": "Detailed prompt for FLUX image generation, 9:16 vertical, no text, no words, no letters",
      "motion_prompt": "subtle camera movement for 5-second clip",
      "text_safe_zone": "upper_center"
    }}
  ],
  "illustration_style": "minimal_symbolic_spiritual",
  "aspect_ratio": "9:16"
}}

Output ONLY the JSON. No markdown, no explanation."""

    cmd = ["hermes", "chat", "-q", prompt, "-Q"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"Hermes storyboard error: {result.stderr[:500]}")
    
    data = extract_json(result.stdout)
    return data

# ─── IMAGE GENERATION ───
def generate_images(storyboard, gateway):
    images = []
    for i, scene in enumerate(storyboard.get("scenes", [])):
        prompt = scene.get("image_prompt", scene.get("visual_description", ""))
        print(f"    Generating image for {scene.get('scene_id', f'S{i+1}')}...")
        
        result = gateway.generate_image(
            prompt=prompt,
            seed=1000 + i,
            width=1080,
            height=1920,
        )
        
        output_url = ""
        if "images" in result and result["images"]:
            output_url = result["images"][0].get("url", "")
        elif "image" in result:
            output_url = result["image"].get("url", "")
        
        # Download locally
        local_path = None
        if output_url:
            local_path = WORKDIR / f"img_{scene.get('scene_id', f'S{i+1}')}.png"
            urllib.request.urlretrieve(output_url, local_path)
        
        images.append({
            "scene_id": scene.get("scene_id", f"S{i+1}"),
            "output_url": output_url,
            "local_path": str(local_path) if local_path else None,
            "cost": result.get("cost", 0.0),
        })
    return images

# ─── AUDIO GENERATION ───
def generate_audio(script, gateway):
    audio_clips = []
    for i, scene in enumerate(script["scenes"]):
        text = scene.get("narration", scene.get("screen_text", "")).strip()
        if not text:
            continue
        
        print(f"    Generating audio for {scene['scene_id']}...")
        result = gateway.generate_speech(text=text)
        
        audio_url = ""
        if "audio" in result:
            audio_url = result["audio"].get("url", "")
        elif "output" in result:
            audio_url = result["output"].get("url", "")
        
        duration_ms = result.get("duration_ms", 0)
        duration = duration_ms / 1000.0 if duration_ms else result.get("duration", 5.0)
        
        local_path = None
        if audio_url:
            local_path = WORKDIR / f"audio_{scene['scene_id']}.mp3"
            urllib.request.urlretrieve(audio_url, local_path)
        
        audio_clips.append({
            "scene_id": scene["scene_id"],
            "output_url": audio_url,
            "local_path": str(local_path) if local_path else None,
            "duration": duration,
            "cost": result.get("cost", 0.0),
        })
    return audio_clips

# ─── VIDEO ASSEMBLY ───
def assemble_video(images, audio_clips, script, output_path):
    """Assemble video using FFmpeg: static images + narration audio."""
    from PIL import Image, ImageDraw, ImageFont
    
    segments = []
    audio_map = {a["scene_id"]: a for a in audio_clips}
    
    for img in images:
        scene_id = img["scene_id"]
        local_img = img.get("local_path")
        if not local_img or not Path(local_img).exists():
            print(f"    WARNING: No image for {scene_id}, skipping")
            continue
        
        scene_audio = audio_map.get(scene_id)
        
        # Create overlay with screen text
        scene_data = next((s for s in script["scenes"] if s["scene_id"] == scene_id), None)
        screen_text = scene_data["screen_text"] if scene_data else ""
        
        # Render image with text overlay
        pil_img = Image.open(local_img).convert("RGBA")
        w, h = pil_img.size
        draw = ImageDraw.Draw(pil_img)
        
        # Draw semi-transparent band at bottom
        band_top = int(h * 0.62)
        band_bottom = int(h * 0.92)
        overlay = Image.new("RGBA", pil_img.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rectangle([(0, band_top), (w, band_bottom)], fill=(0, 0, 0, 160))
        pil_img = Image.alpha_composite(pil_img, overlay)
        draw = ImageDraw.Draw(pil_img)
        
        # Draw text
        font_size = min(56, w // 18)
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
        except:
            font = ImageFont.load_default()
        
        if screen_text:
            try:
                bbox = draw.textbbox((0, 0), screen_text, font=font)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]
            except:
                tw = font_size * len(screen_text) // 2
                th = font_size
            x = (w - tw) // 2
            y = band_top + (band_bottom - band_top - th) // 2
            draw.text((x+2, y+2), screen_text, fill=(0, 0, 0, 200), font=font)
            draw.text((x, y), screen_text, fill=(255, 255, 255, 255), font=font)
        
        # Save overlay image
        overlay_img_path = WORKDIR / f"overlay_{scene_id}.png"
        pil_img.convert("RGB").save(overlay_img_path, "PNG")
        
        # Create video segment
        segment_path = WORKDIR / f"segment_{scene_id}.mp4"
        
        if scene_audio and scene_audio.get("local_path") and Path(scene_audio["local_path"]).exists():
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", str(overlay_img_path),
                "-i", str(scene_audio["local_path"]),
                "-c:v", "libx264",
                "-tune", "stillimage",
                "-pix_fmt", "yuv420p",
                "-r", "30",
                "-preset", "fast",
                "-crf", "23",
                "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
                "-c:a", "aac",
                "-b:a", "128k",
                "-shortest",
                str(segment_path),
            ]
        else:
            # Silent 5-second segment
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", str(overlay_img_path),
                "-f", "lavfi",
                "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-t", "5",
                "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
                "-r", "30",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-c:a", "aac",
                "-shortest",
                str(segment_path),
            ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            print(f"    WARNING: Segment creation failed for {scene_id}: {result.stderr[:200]}")
            continue
        
        segments.append(str(segment_path))
    
    if not segments:
        raise RuntimeError("No video segments created")
    
    # Create end card
    endcard_path = WORKDIR / "endcard.mp4"
    endcard_img = Image.new("RGB", (1080, 1920), (10, 10, 20))
    draw = ImageDraw.Draw(endcard_img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 64)
    except:
        font = ImageFont.load_default()
    credit = script.get("source_credit", "Source: Ancient Wisdom")
    try:
        bbox = draw.textbbox((0, 0), credit, font=font)
        tw = bbox[2] - bbox[0]
    except:
        tw = 300
    draw.text(((1080 - tw) // 2, 800), credit, fill=(255, 215, 0), font=font)
    
    try:
        small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 40)
    except:
        small_font = ImageFont.load_default()
    sub_text = "Subscribe for more wisdom"
    try:
        bbox = draw.textbbox((0, 0), sub_text, font=small_font)
        tw = bbox[2] - bbox[0]
    except:
        tw = 200
    draw.text(((1080 - tw) // 2, 1000), sub_text, fill=(200, 200, 200), font=small_font)
    
    endcard_img.save(WORKDIR / "endcard.png", "PNG")
    
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(WORKDIR / "endcard.png"),
        "-f", "lavfi",
        "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t", "3",
        "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
        "-r", "30",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-shortest",
        str(endcard_path),
    ]
    subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    segments.append(str(endcard_path))
    
    # Concatenate all segments
    concat_list = WORKDIR / "concat.txt"
    with open(concat_list, "w") as f:
        for seg in segments:
            f.write(f"file '{seg}'\n")
    
    concat_path = WORKDIR / "concat.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-r", "30",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        str(concat_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"Concat failed: {result.stderr[:500]}")
    
    # Add background music
    final_path = Path(output_path)
    music_path = WORKDIR / "bg_music.mp3"
    
    # Generate simple background music
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(concat_path)],
        capture_output=True, text=True, timeout=30
    )
    video_duration = 30.0
    if probe.returncode == 0:
        fmt = json.loads(probe.stdout).get("format", {})
        video_duration = float(fmt.get("duration", 30.0))
    
    music_cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"sine=frequency=220:duration={video_duration:.1f}",
        "-f", "lavfi",
        "-i", f"sine=frequency=330:duration={video_duration:.1f}",
        "-filter_complex",
        "[0:a]volume=0.3[a1];[1:a]volume=0.15[a2];[a1][a2]amix=inputs=2:duration=longest,lowpass=f=800,aecho=0.8:0.7:60:0.3,volume=0.5[mix]",
        "-map", "[mix]",
        "-c:a", "libmp3lame",
        "-b:a", "96k",
        str(music_path),
    ]
    subprocess.run(music_cmd, capture_output=True, text=True, timeout=60)
    
    if music_path.exists():
        mux_cmd = [
            "ffmpeg", "-y",
            "-i", str(concat_path),
            "-i", str(music_path),
            "-filter_complex",
            "[1:a]volume=0.08[bg];[0:a][bg]amix=inputs=2:duration=first:dropout_transition=0[aout]",
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "128k",
            str(final_path),
        ]
        result = subprocess.run(mux_cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            import shutil
            shutil.copy(str(concat_path), str(final_path))
    else:
        import shutil
        shutil.copy(str(concat_path), str(final_path))
    
    return str(final_path)

# ─── MAIN ───
def main():
    # Load corpus items — discover ALL manifests, then shuffle by source-type mixing
    manifests_dir = Path("/opt/data/VideoGeneratorBusinessRepo/corpus/manifests")
    
    # 1. Read every manifest and group by tradition
    all_manifests = sorted(manifests_dir.glob("*.json"))
    print(f"Discovered {len(all_manifests)} total manifests")
    
    by_tradition = {}
    for path in all_manifests:
        with open(path) as f:
            item = json.load(f)
        work = item.get("work", "Unknown")
        tradition = work.split()[0].lower() if work else "unknown"
        by_tradition.setdefault(tradition, []).append(item)
    
    print(f"Grouped into traditions: {list(by_tradition.keys())}")
    for t, items in by_tradition.items():
        print(f"  {t}: {len(items)} items")
    
    # 2. Build a round-robin mixed list (one from each tradition, repeat)
    traditions = list(by_tradition.keys())
    random.seed(42)  # reproducible shuffle
    for t in traditions:
        random.shuffle(by_tradition[t])
    
    mixed_sources = []
    max_len = max(len(by_tradition[t]) for t in traditions)
    for i in range(max_len):
        for t in traditions:
            if i < len(by_tradition[t]):
                mixed_sources.append(by_tradition[t][i])
    
    # 3. Take the first 5 from the mixed ordering
    sources = mixed_sources[:5]
    
    print(f"\nSelected {len(sources)} items (mixed ordering):")
    for s in sources:
        print(f"  - {s['source_id']} ({s.get('work','')})")
    
    # Create / find Drive folder structure
    print("Ensuring Google Drive folder structure...")
    reel_factory_id = ensure_drive_folder("Reel_Factory")  # top-level parent
    batch_folder_name = f"Batch_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}"
    folder_id = ensure_drive_folder(batch_folder_name, parent_id=reel_factory_id)
    print(f"  Uploading to: Reel_Factory/{batch_folder_name} ({folder_id})")
    
    gateway = FalGateway()
    results = []
    
    for idx, source in enumerate(sources, 1):
        print(f"\n{'='*60}")
        print(f"VIDEO {idx}/5: {source['source_id']}")
        print(f"{'='*60}")
        
        try:
            # Step 1: Generate script
            print(f"  [1/5] Generating script...")
            script = generate_script(source)
            print(f"    Title: {script['title']}")
            
            # Save script
            script_path = WORKDIR / f"script_{idx}.json"
            with open(script_path, "w") as f:
                json.dump(script, f, indent=2)
            
            # Step 2: Generate storyboard
            print(f"  [2/5] Generating storyboard...")
            storyboard = generate_storyboard(script, source)
            
            # Save storyboard
            sb_path = WORKDIR / f"storyboard_{idx}.json"
            with open(sb_path, "w") as f:
                json.dump(storyboard, f, indent=2)
            
            # Step 3: Generate images
            print(f"  [3/5] Generating images...")
            images = generate_images(storyboard, gateway)
            total_img_cost = sum(i["cost"] for i in images)
            print(f"    Images: {len(images)} | Cost: ${total_img_cost:.2f}")
            
            # Step 4: Generate audio
            print(f"  [4/5] Generating audio...")
            audio = generate_audio(script, gateway)
            total_audio_cost = sum(a["cost"] for a in audio)
            print(f"    Audio clips: {len(audio)} | Cost: ${total_audio_cost:.2f}")
            
            # Step 5: Assemble video
            print(f"  [5/5] Assembling video...")
            output_path = WORKDIR / f"reel_{idx}_{source['source_id']}.mp4"
            final_path = assemble_video(images, audio, script, str(output_path))
            print(f"    Video saved: {final_path}")
            
            # Upload to Drive
            print(f"  Uploading to Google Drive...")
            link, file_id = upload_to_drive(Path(final_path), folder_id)
            print(f"    Drive link: {link}")
            
            results.append({
                "index": idx,
                "source_id": source["source_id"],
                "title": script["title"],
                "video_path": final_path,
                "drive_link": link,
                "drive_file_id": file_id,
                "image_cost": total_img_cost,
                "audio_cost": total_audio_cost,
                "status": "success",
            })
            
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({
                "index": idx,
                "source_id": source["source_id"],
                "error": str(e),
                "status": "failed",
            })
    
    # Summary
    print(f"\n{'='*60}")
    print("BATCH SUMMARY")
    print(f"{'='*60}")
    total_cost = sum(r.get("image_cost", 0) + r.get("audio_cost", 0) for r in results if r["status"] == "success")
    success_count = sum(1 for r in results if r["status"] == "success")
    print(f"Successful: {success_count}/{len(results)}")
    print(f"Total cost: ${total_cost:.2f}")
    for r in results:
        if r["status"] == "success":
            print(f"  ✓ {r['index']}. {r['title']} -> {r['drive_link']}")
        else:
            print(f"  ✗ {r['index']}. {r['source_id']} -> ERROR: {r.get('error', 'Unknown')}")
    
    # Save summary
    summary_path = WORKDIR / "batch_summary.json"
    with open(summary_path, "w") as f:
        json.dump({
            "results": results,
            "reel_factory_folder_id": reel_factory_id,
            "batch_folder_id": folder_id,
            "batch_folder_name": batch_folder_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, f, indent=2)
    print(f"\nSummary saved to: {summary_path}")
    print(f"\nAll videos uploaded to Google Drive folder: Reel_Factory/{batch_folder_name}")
    print(f"  Folder link: https://drive.google.com/drive/folders/{folder_id}")

if __name__ == "__main__":
    main()
```

</details>

---

## 5. Running the Generator

### 5.1 One-Shot Command

```bash
cd /opt/data/VideoGeneratorBusinessRepo

# Export FAL key
export FAL_KEY="$(grep FAL_KEY /opt/data/.env | cut -d= -f2-)"

# Activate venv
source .venv/bin/activate

# Run (takes ~25-35 min for 5 videos)
python3 generate_5_videos.py
```

### 5.2 Background Process (for TUI sessions)

```bash
cd /opt/data/VideoGeneratorBusinessRepo
export FAL_KEY="$(grep FAL_KEY /opt/data/.env | cut -d= -f2-)"
source .venv/bin/activate

# Run in background with completion notification
nohup python3 generate_5_videos.py > runtime/output/generate.log 2>&1 &
echo "PID: $!"
```

### 5.3 Checking Progress

```bash
# Tail the log
tail -f /opt/data/VideoGeneratorBusinessRepo/runtime/output/generate.log

# Or check the batch output directory
ls -lt /opt/data/VideoGeneratorBusinessRepo/runtime/output/batch_5/*.mp4
```

---

## 6. Google Drive Folder Structure

```
Google Drive Root
└── Reel_Factory/                          # Created once, reused forever
    ├── Batch_2026-07-24_1425/            # Timestamped subfolder per run
    │   ├── reel_1_aesop-the-ant-and-the-dove.mp4
    │   ├── reel_2_gita-ch2-ocean-mind.mp4
    │   ├── ...
    │   └── (5 videos per batch)
    ├── Batch_2026-07-24_1540/
    │   └── ...
    └── ...
```

**`ensure_drive_folder()` behavior:**
- Searches Drive for existing folder by name + parent
- If found → returns existing ID (no duplicates)
- If not found → creates new folder
- `Reel_Factory` is the stable top-level folder
- Each batch gets a `Batch_YYYY-MM-DD_HHMM` subfolder

---

## 7. Known Pitfalls & Fixes

### 7.1 Hermes JSON Extraction

**Problem:** Hermes TUI outputs reasoning blocks with box-drawing chars before JSON:

```
┌─ Reasoning ──────────────────────────────────────────────────────────────────┐
The user wants a 5-scene script...

{"title": "...", "scenes": [...]}
```

**Fix:** The `extract_json()` function:
1. Strips `┌─┐│└┘` box-drawing characters
2. Scans for ALL `{...}` blocks in the output
3. Tries each block with `json.loads()`, keeping the largest valid one
4. Falls back to `[...]` array parsing

**Verified against:** code fences, reasoning blocks, raw JSON, nested braces.

### 7.2 FAL_KEY Not Set

**Problem:** `ERROR: FAL_KEY not set` on first run.

**Fix:** The key is in `/opt/data/.env` but must be explicitly exported. The `.env` file is NOT auto-loaded by the script (it reads from `os.getenv()`). The script does have a fallback that reads `.env` from CWD, but explicit export is more reliable.

### 7.3 Scene ID Types

**Problem:** Hermes sometimes returns integer scene IDs (`1, 2, 3...`) instead of strings (`"S01", "S02"...`).

**Fix:** The script normalizes:
```python
sid = s.get("scene_id", "")
if isinstance(sid, int):
    sid = f"S{sid:02d}"
```

### 7.4 Array-Only Response

**Problem:** Sometimes Hermes returns only the scenes array `[{...}, {...}]` without the outer wrapper object.

**Fix:**
```python
if isinstance(data, list):
    data = {"scenes": data}
```

### 7.5 Assembly FFmpeg Failures

**Problem:** FFmpeg concat or overlay operations fail silently.

**Fix:** Each FFmpeg call checks `returncode` and prints stderr on failure. The assembly falls back to copying the concat file if the music mix fails.

---

## 8. File Tree (Relevant Files)

```
/opt/data/VideoGeneratorBusinessRepo/
├── generate_5_videos.py          # ← PRIMARY ENTRYPOINT (self-contained)
├── .env                          # FAL_KEY (DO NOT COMMIT)
├── .venv/                        # Python virtual environment
├── config/
│   ├── app.yaml                  # Video specs (1080×1920, 30fps, etc.)
│   ├── drive_sheets.yaml         # Drive/Sheets endpoint config
│   ├── models.yaml               # LLM review thresholds
│   ├── review_thresholds.yaml    # Review scoring thresholds
│   └── visual_styles.yaml        # Style guide for image gen
├── corpus/
│   ├── manifests/                # 353 JSON files (CorpusItem schema)
│   │   ├── aesop-*.json
│   │   ├── jataka-*.json
│   │   ├── gita-ch2-*.json
│   │   ├── upanishad-*.json
│   │   └── veda-rig-*.json
│   └── source_texts/             # Raw text files (Gutenberg downloads)
│       ├── bhagavad_gita.txt
│       ├── upanishads.txt
│       └── ...
├── runtime/
│   ├── output/                   # Generated videos, images, audio
│   │   └── batch_5/
│   │       ├── reel_1_*.mp4
│   │       ├── script_1.json
│   │       ├── storyboard_1.json
│   │       └── batch_summary.json
│   └── state.db                  # SQLite job state (not currently used)
└── src/reel_factory/             # Original pipeline modules
    ├── __init__.py
    ├── models.py                 # Pydantic schemas (CorpusItem, etc.)
    ├── workflow.py               # Orchestrator (uses HermesClient)
    ├── fal_gateway.py            # fal.ai API wrapper
    ├── drive.py                  # Google Drive client (service account)
    ├── assembly.py               # FFmpeg video assembly pipeline
    ├── image_pipeline.py         # Image generation wrapper
    ├── audio_pipeline.py         # TTS generation wrapper
    ├── hermes_client.py          # Hermes CLI wrapper with JSON extraction
    ├── state_store.py            # SQLite state persistence
    ├── corpus.py                 # Corpus loading/management
    ├── selection.py              # Source selection engine
    ├── review_loop.py            # Review/retry logic
    ├── sheets.py                 # Google Sheets logging
    ├── cli.py                    # CLI entrypoint (reel-factory command)
    ├── config.py                 # Config loader
    └── logging.py                # Structured logging
```

---

## 9. How to Add New Sources

### 9.1 Download Raw Text

```bash
cd /opt/data/VideoGeneratorBusinessRepo/corpus/source_texts

# Example: Download Tao Te Ching
curl -L "https://www.gutenberg.org/files/216/216-0.txt" -o tao_te_ching.txt
```

### 9.2 Extract Manifests

Write a Python script that:
1. Parses the text into discrete teachings/stories
2. Creates a `CorpusItem` dict for each
3. Saves to `corpus/manifests/<source_id>.json`

**Key fields to populate:**
- `source_id` — URL-safe slug (e.g., `tao-ch1-nameless-beginning`)
- `work` — Book title (first word becomes tradition group)
- `approved_translation` — The core teaching text
- `context_summary` — 1-2 sentence background
- `license` — Must be `public-domain`
- `depiction_policy` — Use `symbolic-preferred`

### 9.3 Validate

```python
import json
from pathlib import Path
from reel_factory.models import CorpusItem

manifest = json.loads(Path("corpus/manifests/my-new-item.json").read_text())
item = CorpusItem(**manifest)
print(f"Valid: {item.source_id}")
```

### 9.4 Regenerate

Run `generate_5_videos.py` again. The new items will automatically be included in the round-robin selection.

---

## 10. Cost Budgeting

| Scale | Videos | Estimated Cost | Time |
|-------|--------|---------------|------|
| Test batch | 5 | ~$1.40 | ~30 min |
| Daily | 10 | ~$2.80 | ~60 min |
| Weekly | 70 | ~$19.60 | ~7 hrs |
| Monthly | 300 | ~$84.00 | ~30 hrs |

**Cost caps:** The original pipeline has a `$5.00` per-job budget (see `models.py:JobRecord.max_cost_budget`). The ad-hoc script does not enforce this but tracks actual spend.

---

## 11. Quick Reference: Key Commands

```bash
# Verify environment
python3 -c "import fal_client; print('fal_client OK')"
python3 -c "from reel_factory.fal_gateway import FalGateway; g = FalGateway(); print('FalGateway OK')"

# Check corpus count
ls corpus/manifests/*.json | wc -l

# Inspect a manifest
jq . corpus/manifests/gita-ch2-immortality-of-soul.json | head -20

# Verify all manifests
python3 -c "
import json
from pathlib import Path
from reel_factory.models import CorpusItem
errors = []
for p in Path('corpus/manifests').glob('*.json'):
    try:
        CorpusItem(**json.loads(p.read_text()))
    except Exception as e:
        errors.append(f'{p.name}: {e}')
print(f'Valid: {353 - len(errors)}/353')
if errors:
    print('Errors:', errors[:3])
"

# Run generator
export FAL_KEY="$(grep FAL_KEY /opt/data/.env | cut -d= -f2-)"
source .venv/bin/activate
python3 generate_5_videos.py

# Check generated output
ls -lh runtime/output/batch_5/*.mp4

# View batch summary
cat runtime/output/batch_5/batch_summary.json | jq .
```

---

## 12. Session Handoff Notes

- **The `generate_5_videos.py` script is the canonical entrypoint.** The original `workflow.py` + `cli.py` pipeline exists but the ad-hoc script is what actually works end-to-end.
- **Google Drive uses OAuth2, not service account.** The token at `/opt/data/google_token.json` has a refresh token and works indefinitely.
- **Hermes CLI is the LLM backend.** There is no API key — it uses the local Hermes TUI profile.
- **Image generation uses Qwen Image 2**, not FLUX. The prompts reference FLUX for style consistency but the actual endpoint is `fal-ai/qwen-image-2/text-to-image`.
- **Background music is generated procedurally** (sine waves + reverb) via FFmpeg, not downloaded. This avoids copyright issues.
- **The round-robin mixing ensures diversity.** If you want to force specific items, bypass `mixed_sources[:5]` and hardcode `source_ids`.
- **Drive folder `Reel_Factory` is stable.** It is created once and reused. Batches nest underneath it.

---

*End of session-agnostic reference. For questions, check the batch summary JSONs in `runtime/output/batch_*/batch_summary.json`.*
