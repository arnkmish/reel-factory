#!/usr/bin/env python3
"""
Generate 5 spiritual wisdom videos and upload to Google Drive.
Uses the Reel Factory pipeline.
"""

import json
import os
import random  # ← added
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
BATCH_NUMBER = Path("/opt/data/VideoGeneratorBusinessRepo/runtime/batch_counter.txt")
if BATCH_NUMBER.exists():
    batch_num = int(BATCH_NUMBER.read_text().strip()) + 1
else:
    batch_num = 6  # First new batch after batch_5
BATCH_NUMBER.write_text(str(batch_num))
WORKDIR = Path(f"/opt/data/VideoGeneratorBusinessRepo/runtime/output/batch_{batch_num}")
WORKDIR.mkdir(parents=True, exist_ok=True)

# Kokoro TTS — American English Voice Options (19 total):
# For clean, easy-to-understand kid narration, pick a clear voice:
#   af_nova   — clear, natural storyteller (RECOMMENDED for kids)
#   af_bella  — bright, articulate
#   af_sarah  — warm, calm narrator
#   af_jessica — friendly, approachable
#   af_ally   — polished, professional
#   af_sharon — mature, wise
#   af_kore   — warm, grandmotherly
#   af_aoede  — melodic, lyrical
#   af_nicole — modern, confident
#   af_sky    — serene, soft-spoken
#   Male (am_*):
#     am_adam   — natural, trustworthy
#     am_michael — clear, articulate
#     am_eric   — warm, steady
#     am_river  — smooth, modern
#     am_puck   — gentle, soothing
#     am_echo   — deep, resonant
#     am_onyx   — calm, authoritative
#     am_santa  — jolly, grandfatherly
#     am_gurney — gentle, scholarly
#
# To change the voice, set this variable before running:
TTS_VOICE = os.getenv("TTS_VOICE", "af_nova")
TTS_SPEED = float(os.getenv("TTS_SPEED", "0.85"))

FAL_KEY = os.getenv("FAL_KEY")

# Track used items to avoid reusing them in future batches
USED_ITEMS_PATH = Path("/opt/data/VideoGeneratorBusinessRepo/runtime/used_items.json")

FAL_KEY = os.getenv("FAL_KEY")
if not FAL_KEY:
    print("ERROR: FAL_KEY not set")
    sys.exit(1)

# ─── ITEM TRACKING ───
def load_used_items() -> set:
    """Load set of previously used source_ids."""
    if USED_ITEMS_PATH.exists():
        with open(USED_ITEMS_PATH) as f:
            data = json.load(f)
            return set(data.get("used_ids", []))
    return set()

def save_used_items(new_ids: list):
    """Append newly used source_ids to history."""
    used = load_used_items()
    used.update(new_ids)
    USED_ITEMS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(USED_ITEMS_PATH, "w") as f:
        json.dump({"used_ids": sorted(list(used))}, f, indent=2)
    print(f"  Total unique items used so far: {len(used)}")

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
    
    # The LLM output usually has reasoning text then JSON.
    # Try to find the first '{' that starts a valid JSON object.
    # We scan forward and track brace depth to find the outermost complete JSON.
    
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
                    # Strip control chars
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
    prompt = f"""Write a 5-scene script for a short vertical **children's moral story** video.

Source: {source_item["work"]} — {source_item["location"]["story"]}
Teaching: {source_item["approved_translation"]}
Context: {source_item["context_summary"]}

Requirements:
- **Language**: Simple, vivid, and easy for children aged 6-12 to understand. No abstract philosophy. Speak the moral clearly.
- **Pacing**: This is for SLOW narration (0.85x speed). Keep each scene's narration SHORT — max 15-20 words. Use simple words. Add natural pauses with commas and periods. Short sentences. One idea per sentence.
- Scene 1: HOOK — a compelling question or statement that grabs a child's attention
- Scenes 2-4: NARRATIVE — tell the story with vivid characters, actions, and emotions
- Scene 5: MORAL — deliver the lesson in a clear, memorable way kids can apply. Include the final_moral text in the narration.
- Each scene needs narration text that tells the story when spoken aloud

Respond with valid JSON only. Use this exact schema:
{{
  "title": "A short compelling title kids would love",
  "hook": "1-2 sentence attention grabber",
  "duration_seconds": 30,
  "scenes": [
    {{"scene_id": "S01", "narration": "1 short sentence (max 15 words)", "story_function": "hook"}},
    {{"scene_id": "S02", "narration": "1-2 short sentences (max 20 words total)", "story_function": "narrative"}},
    {{"scene_id": "S03", "narration": "1-2 short sentences (max 20 words total)", "story_function": "narrative"}},
    {{"scene_id": "S04", "narration": "1-2 short sentences (max 20 words total)", "story_function": "narrative"}},
    {{"scene_id": "S05", "narration": "1-2 short sentences ending with the moral (max 20 words)", "story_function": "moral"}}
  ],
  "final_moral": "The core lesson in 1 simple sentence",
  "source_credit": "Source: {source_item['work']}",
  "caption": "A short social media caption for parents",
  "hashtags": ["#moralstory", "#kids", "#fable"]
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
        f"  {s['scene_id']} ({s['story_function']}): narration='{s['narration']}'"
        for s in script["scenes"]
    )
    
    prompt = f"""Create a 5-scene storyboard for a vertical video.

Title: {script['title']}
Hook: {script['hook']}
Scenes:
{scenes_text}
Final moral: {script['final_moral']}

Requirements:
- Each scene needs: scene_id, visual_description, characters (list), setting, composition, camera, palette (list), symbols (list), image_prompt, motion_prompt
- image_prompt must be specific, descriptive, match the story content
- Style: bright vivid children's book illustration, clear expressive characters, warm colors, 9:16 vertical
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
      "motion_prompt": "subtle camera movement for 5-second clip"
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
def generate_audio(script, gateway, voice=None, speed=None):
    voice = voice or TTS_VOICE
    speed = speed or TTS_SPEED
    audio_clips = []
    total_duration = 0.0
    for i, scene in enumerate(script["scenes"]):
        text = scene.get("narration", "").strip()
        if not text:
            continue
        
        # Append final_moral to Scene 5 so the moral IS spoken
        if scene.get("scene_id") == "S05" and script.get("final_moral"):
            text = text + " " + script["final_moral"].strip()
        
        print(f"    Generating audio for {scene['scene_id']}... (voice: {voice}, speed: {speed})")
        result = gateway.generate_speech(text=text, voice=voice, speed=speed)
        
        audio_url = ""
        if "audio" in result:
            audio_url = result["audio"].get("url", "")
        elif "output" in result:
            audio_url = result["output"].get("url", "")
        
        local_path = None
        if audio_url:
            local_path = WORKDIR / f"audio_{scene['scene_id']}.wav"
            urllib.request.urlretrieve(audio_url, local_path)
        
        # Get ACTUAL WAV duration via ffprobe
        duration = 5.0
        if local_path and Path(local_path).exists():
            probe = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_format", str(local_path)],
                capture_output=True, text=True, timeout=30,
            )
            if probe.returncode == 0:
                import json
                fmt = json.loads(probe.stdout).get("format", {})
                duration = float(fmt.get("duration", 5.0))
        
        total_duration += duration
        audio_clips.append({
            "scene_id": scene["scene_id"],
            "output_url": audio_url,
            "local_path": str(local_path) if local_path else None,
            "duration": duration,
            "cost": result.get("cost", 0.0),
        })
    
    # Sanity check: total audio duration
    print(f"    Total narration duration: {total_duration:.1f}s")
    if total_duration < 15:
        print(f"    WARNING: Total audio is only {total_duration:.1f}s — narration may be too brief")
    elif total_duration > 45:
        print(f"    WARNING: Total audio is {total_duration:.1f}s — narration may be too long for kids")
    
    return audio_clips

# ─── VIDEO ASSEMBLY ───
def assemble_video(images, audio_clips, script, output_path):
    """Assemble video using FFmpeg: static images + narration audio."""
    
    # Create per-scene segments
    segments = []
    audio_map = {a["scene_id"]: a for a in audio_clips}
    
    for img in images:
        scene_id = img["scene_id"]
        local_img = img.get("local_path")
        if not local_img or not Path(local_img).exists():
            print(f"    WARNING: No image for {scene_id}, skipping")
            continue
        
        scene_audio = audio_map.get(scene_id)
        
        # Use the generated image directly (no text overlay burned in)
        segment_path = WORKDIR / f"segment_{scene_id}.mp4"
        
        if scene_audio and scene_audio.get("local_path") and Path(scene_audio["local_path"]).exists():
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", str(local_img),
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
            # Silent 5-second segment — match TTS audio format (24000 Hz mono)
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", str(local_img),
                "-f", "lavfi",
                "-i", "anullsrc=channel_layout=mono:sample_rate=24000",
                "-t", "5",
                "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
                "-r", "30",
                "-c:v", "libx264",
                "-tune", "stillimage",
                "-pix_fmt", "yuv420p",
                "-preset", "fast",
                "-crf", "23",
                "-c:a", "aac",
                "-ar", "24000",
                "-ac", "1",
                "-b:a", "128k",
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
    
    # Create end card (plain solid color, no text overlays)
    # IMPORTANT: endcard audio must match the TTS segments' audio format
    # (24000 Hz mono) to avoid FFmpeg concat demuxer audio duration skew.
    endcard_path = WORKDIR / "endcard.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "color=c=0x0a0a14:size=1080x1920:rate=30",
        "-f", "lavfi",
        "-i", "anullsrc=channel_layout=mono:sample_rate=24000",
        "-t", "3",
        "-pix_fmt", "yuv420p",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-ar", "24000",
        "-ac", "1",
        "-b:a", "128k",
        "-shortest",
        str(endcard_path),
    ]
    subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    segments.append(str(endcard_path))
    # Concatenate all segments using the concat filter (handles any remaining
    # format mismatches by normalizing all inputs to a common format).
    num_segments = len(segments)
    concat_inputs = []
    for seg in segments:
        concat_inputs.extend(["-i", seg])
    filter_inputs = "".join(
        f"[{i}:v][{i}:a]" for i in range(num_segments)
    )
    concat_path = WORKDIR / "concat.mp4"
    cmd = [
        "ffmpeg", "-y",
        *concat_inputs,
        "-filter_complex",
        f"{filter_inputs}concat=n={num_segments}:v=1:a=1[v][a]",
        "-map", "[v]",
        "-map", "[a]",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-r", "30",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-ar", "24000",
        "-ac", "1",
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
            "-ar", "24000",
            "-ac", "1",
            "-b:a", "128k",
            "-shortest",
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
    
    # ── KID-FRIENDLY FILTER ─────────────────────────────────────
    # Only include fables and stories with clear moral lessons for children.
    # Excludes abstract philosophy (Bhagavad Gita, Upanishads, Vedas).
    KID_FRIENDLY_TRADITIONS = {"aesop's", "jataka", "panchatantra", "indian"}
    kid_friendly = {}
    for t in traditions:
        if t in KID_FRIENDLY_TRADITIONS:
            kid_friendly[t] = by_tradition[t]
    if not kid_friendly:
        print("WARNING: No kid-friendly items found. Falling back to all items.")
        kid_friendly = by_tradition
    traditions = list(kid_friendly.keys())
    by_tradition = kid_friendly
    # ────────────────────────────────────────────────────────────
    
    random.seed(42)  # reproducible shuffle
    for t in traditions:
        random.shuffle(by_tradition[t])
    
    # Filter out previously used items
    used_ids = load_used_items()
    print(f"  Filtering out {len(used_ids)} previously used items...")
    
    fresh_by_tradition = {}
    for t in traditions:
        fresh = [item for item in by_tradition[t] if item["source_id"] not in used_ids]
        fresh_by_tradition[t] = fresh
        skipped = len(by_tradition[t]) - len(fresh)
        if skipped:
            print(f"    {t}: {len(fresh)} fresh, {skipped} skipped")
    
    # Check if we have enough fresh items
    total_fresh = sum(len(fresh_by_tradition[t]) for t in traditions)
    if total_fresh < 5:
        print(f"  WARNING: Only {total_fresh} fresh items remaining. Resetting used items...")
        save_used_items([])
        fresh_by_tradition = by_tradition  # use all items
        used_ids = set()
    
    mixed_sources = []
    max_len = max(len(fresh_by_tradition[t]) for t in traditions)
    for i in range(max_len):
        for t in traditions:
            if i < len(fresh_by_tradition[t]):
                mixed_sources.append(fresh_by_tradition[t][i])
    
    # 3. Take the first 5 from the mixed ordering
    sources = mixed_sources[:5]
    
    # Track selected items to avoid reuse in future batches
    selected_ids = [s["source_id"] for s in sources]
    save_used_items(selected_ids)
    
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
