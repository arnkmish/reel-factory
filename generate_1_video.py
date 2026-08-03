#!/usr/bin/env python3
"""
Generate a SINGLE children's moral story video and upload to Google Drive.
Uses the same pipeline as generate_5_videos.py but produces just 1 video.

Usage:
    export FAL_KEY="..."
    export TTS_VOICE="af_nova"  # optional
    export TTS_SPEED="0.85"     # optional, 0.85 = slow kid-friendly pace
    python generate_1_video.py
"""

import json
import os
import random
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Add the project src to path
sys.path.insert(0, "/opt/data/VideoGeneratorBusinessRepo/src")

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from reel_factory.fal_gateway import FalGateway

# ─── CONFIG ───
BATCH_NUMBER = Path("/opt/data/VideoGeneratorBusinessRepo/runtime/batch_counter.txt")
if BATCH_NUMBER.exists():
    batch_num = int(BATCH_NUMBER.read_text().strip()) + 1
else:
    batch_num = 1
BATCH_NUMBER.write_text(str(batch_num))

WORKDIR = Path(f"/opt/data/VideoGeneratorBusinessRepo/runtime/output/single_{batch_num}")
WORKDIR.mkdir(parents=True, exist_ok=True)

# ByteDance Seed Speech TTS — Available voices:
#   stokie_en   — clear English (DEFAULT — safest for storytelling)
#   dacey_en    — warm English storyteller
#   tim_en      — steady English narrator
#   mindy_en_es_id_pt_zh — multilingual, good range
#
# If voice sounds weird, try another by setting:
#   export TTS_VOICE="stokie_en"
# Then run again.
#
# Speed is now configurable: export TTS_SPEED="0.88" (default)
#   Lower = slower (e.g. 0.75), Higher = faster (e.g. 1.0)
TTS_VOICE = os.getenv("TTS_VOICE", "stokie_en")
TTS_SPEED = float(os.getenv("TTS_SPEED", "0.88"))

FAL_KEY = os.getenv("FAL_KEY")
if not FAL_KEY:
    print("ERROR: FAL_KEY not set")
    sys.exit(1)

USED_ITEMS_PATH = Path("/opt/data/VideoGeneratorBusinessRepo/runtime/used_items.json")

# ─── ITEM TRACKING ───
def load_used_items() -> set:
    if USED_ITEMS_PATH.exists():
        with open(USED_ITEMS_PATH) as f:
            data = json.load(f)
            return set(data.get("used_ids", []))
    return set()

def save_used_items(new_ids: list):
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
    query = f"mimeType='application/vnd.google-apps.folder' and name='{name}' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    results = service.files().list(q=query, spaces='drive', fields='files(id, name)', pageSize=1).execute()
    items = results.get('files', [])
    if items:
        print(f"    Found existing folder '{name}': {items[0]['id']}")
        return items[0]['id']
    file_metadata = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        file_metadata["parents"] = [parent_id]
    folder = service.files().create(body=file_metadata, fields="id").execute()
    print(f"    Created new folder '{name}': {folder.get('id')}")
    return folder.get("id")

# ─── HERMES JSON EXTRACTION ───
def extract_json(raw):
    import re
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
    raise ValueError(f"Could not extract JSON from: {raw[:500]}")

# ─── SCRIPT GENERATION ───
def generate_script(source_item):
    prompt = f"""Write a 5-scene script for a short vertical **children's moral story** video.

Source: {source_item["work"]} — {source_item["location"]["story"]}
Teaching: {source_item["approved_translation"]}
Context: {source_item["context_summary"]}

Requirements:
- **Language**: Simple, vivid, and easy for children aged 6-12. No abstract philosophy.
- **Brevity**: Each scene's narration must be EXTREMELY SHORT — max 10-12 words. Short sentences. One idea per scene. Do NOT be verbose.
- **Characters**: Identify 2-3 main characters and use them consistently across all 5 scenes.
- Scene 1: HOOK — one short question or statement (max 10 words)
- Scenes 2-4: NARRATIVE — one simple sentence per scene (max 12 words)
- Scene 5: MORAL — one short sentence with the lesson (max 12 words)
- Total narration must fit under 30 seconds when spoken naturally

Respond with valid JSON only. Use this exact schema:
{{
  "title": "A short compelling title kids would love",
  "hook": "1-2 sentence attention grabber",
  "duration_seconds": 30,
  "scenes": [
    {{"scene_id": "S01", "narration": "One short sentence here.", "story_function": "hook"}},
    {{"scene_id": "S02", "narration": "One simple sentence.", "story_function": "narrative"}},
    {{"scene_id": "S03", "narration": "One simple sentence.", "story_function": "narrative"}},
    {{"scene_id": "S04", "narration": "One simple sentence.", "story_function": "narrative"}},
    {{"scene_id": "S05", "narration": "One short moral sentence.", "story_function": "moral"}}
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
- image_prompt must be specific and descriptive
  - S01: Write a FULL description for generating from scratch (include all characters, setting, style)
  - S02-S05: Write an EDIT instruction describing what changed from the previous scene. Keep the SAME characters with the SAME appearance, clothes, and colors. Only describe the new pose, action, or background change.
- CRITICAL: All 5 scenes must show THE SAME main characters with CONSISTENT appearance (same clothes, same colors, same animal type). Do NOT change character designs between scenes.
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
      "image_prompt": "S01: full generation prompt. S02+: edit instruction — keep same characters, only describe new pose or background","motion_prompt": "subtle camera movement for 5-second clip"
    }}
  ],
  "illustration_style": "bright_childrens_book",
  "aspect_ratio": "9:16"
}}

Output ONLY the JSON. No markdown, no explanation."""

    cmd = ["hermes", "chat", "-q", prompt, "-Q"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"Hermes storyboard error: {result.stderr[:500]}")
    data = extract_json(result.stdout)
    return data

# ─── IMAGE GENERATION (with character consistency via image-to-image editing) ───
def generate_images(storyboard, gateway):
    """Generate images with character consistency via sequential editing.

    Scene 1 is generated from scratch. Scenes 2+ use image-to-image editing
    (qwen-image-edit-2511) on the PREVIOUS scene's image, which preserves
    character appearance (face, clothes, colors) while adapting to the new scene.
    """
    images = []
    previous_url = None
    for i, scene in enumerate(storyboard.get("scenes", [])):
        sid = scene.get("scene_id", f"S{i+1}")
        prompt = scene.get("image_prompt", scene.get("visual_description", ""))
        if i == 0 or not previous_url:
            print(f"    Generating image for {sid} (from scratch)...")
            result = gateway.generate_image(
                prompt=prompt,
                seed=1000 + i,
                width=1080,
                height=1920,
            )
        else:
            print(f"    Generating image for {sid} (editing previous for consistency)...")
            result = gateway.edit_image(
                prompt=prompt,
                image_url=previous_url,
                seed=1000 + i,
                width=1080,
                height=1920,
            )
        output_url = ""
        if "images" in result and result["images"]:
            output_url = result["images"][0].get("url", "")
        elif "image" in result:
            output_url = result["image"].get("url", "")
        local_path = None
        if output_url:
            local_path = WORKDIR / f"img_{sid}.png"
            urllib.request.urlretrieve(output_url, local_path)
            previous_url = output_url  # chain to next scene
        images.append({
            "scene_id": sid,
            "output_url": output_url,
            "local_path": str(local_path) if local_path else None,
            "cost": result.get("cost", 0.0),
        })
    return images

# ─── AUDIO GENERATION (ByteDance Seed Speech) ───
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
        result = gateway.generate_speech_seed(text=text, voice=voice, speed=speed)
        audio_url = ""
        if "audio" in result:
            audio_url = result["audio"].get("url", "")
        elif "output" in result:
            audio_url = result["output"].get("url", "")
        local_path = None
        if audio_url:
            local_path = WORKDIR / f"audio_{scene['scene_id']}.mp3"
            urllib.request.urlretrieve(audio_url, local_path)
        # Get ACTUAL MP3 duration via ffprobe
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
    print(f"    Total narration duration: {total_duration:.1f}s")
    if total_duration < 15:
        print(f"    WARNING: Total audio is only {total_duration:.1f}s — narration may be too brief")
    elif total_duration > 45:
        print(f"    WARNING: Total audio is {total_duration:.1f}s — narration may be too long for kids")
    return audio_clips

# ─── VIDEO ASSEMBLY ───
def assemble_video(images, audio_clips, script, output_path):
    """Assemble video using FFmpeg: static images + narration audio."""
    segments = []
    audio_map = {a["scene_id"]: a for a in audio_clips}
    for img in images:
        scene_id = img["scene_id"]
        local_img = img.get("local_path")
        if not local_img or not Path(local_img).exists():
            print(f"    WARNING: No image for {scene_id}, skipping")
            continue
        scene_audio = audio_map.get(scene_id)
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

    # Concatenate all segments using the concat filter
    num_segments = len(segments)
    concat_inputs = []
    for seg in segments:
        concat_inputs.extend(["-i", seg])
    filter_inputs = "".join(
        f"[{i}:v][{i}:a]" for i in range(num_segments)
    )
    narration_path = WORKDIR / "narration_only.mp4"
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
        str(narration_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg concat failed: {result.stderr[:500]}")

    # Get actual video duration for background music
    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", str(narration_path)],
        capture_output=True, text=True, timeout=30,
    )
    video_duration = 30.0
    if probe.returncode == 0:
        fmt = json.loads(probe.stdout).get("format", {})
        video_duration = float(fmt.get("duration", 30.0))

    # Generate gentle ambient background music using multiple harmonics
    music_path = WORKDIR / "bg_music.mp3"
    music_cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"aevalsrc=0.3*sin(2*PI*220*t)+0.15*sin(2*PI*330*t)+0.1*sin(2*PI*440*t)+0.05*sin(2*PI*550*t):s=24000:d={video_duration:.1f}",
        "-af", "lowpass=f=600,aecho=0.6:0.4:80:0.2,volume=0.08",
        "-c:a", "libmp3lame",
        "-b:a", "96k",
        str(music_path),
    ]
    subprocess.run(music_cmd, capture_output=True, text=True, timeout=60)

    # Mix narration + background music, trim to shortest
    final_path = Path(output_path)
    if music_path.exists():
        mux_cmd = [
            "ffmpeg", "-y",
            "-i", str(narration_path),
            "-i", str(music_path),
            "-filter_complex",
            "[0:a]volume=1.0[na];[1:a]volume=1.0[bg];[na][bg]amix=inputs=2:duration=shortest[aout]",
            "-map", "0:v",
            "-map", "[aout]",
            "-c:v", "copy",
            "-c:a", "aac",
            "-ar", "24000",
            "-ac", "1",
            "-b:a", "128k",
            str(final_path),
        ]
        result = subprocess.run(mux_cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            import shutil
            shutil.copy(str(narration_path), str(final_path))
    else:
        import shutil
        shutil.copy(str(narration_path), str(final_path))
    return str(final_path)

# ─── MAIN ───
def main():
    manifests_dir = Path("/opt/data/VideoGeneratorBusinessRepo/corpus/manifests")
    all_manifests = sorted(manifests_dir.glob("*.json"))
    print(f"Discovered {len(all_manifests)} total manifests")
    
    by_tradition = {}
    for path in all_manifests:
        with open(path) as f:
            item = json.load(f)
        work = item.get("work", "Unknown")
        tradition = work.split()[0].lower() if work else "unknown"
        by_tradition.setdefault(tradition, []).append(item)
    
    # ── KID-FRIENDLY FILTER ──
    KID_FRIENDLY_TRADITIONS = {"aesop's", "jataka", "panchatantra", "indian"}
    kid_friendly = {t: items for t, items in by_tradition.items() if t in KID_FRIENDLY_TRADITIONS}
    if not kid_friendly:
        print("WARNING: No kid-friendly items found. Falling back to all items.")
        kid_friendly = by_tradition
    traditions = list(kid_friendly.keys())
    by_tradition = kid_friendly
    
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
    
    total_fresh = sum(len(fresh_by_tradition[t]) for t in traditions)
    if total_fresh < 1:
        print(f"  WARNING: Only {total_fresh} fresh items remaining. Resetting used items...")
        save_used_items([])
        fresh_by_tradition = by_tradition
        used_ids = set()
    
    # Pick ONE random fresh item from any tradition
    all_fresh = []
    for t in traditions:
        all_fresh.extend(fresh_by_tradition[t])
    random.seed()
    source = random.choice(all_fresh)
    
    print(f"\n{'='*60}")
    print(f"GENERATING SINGLE VIDEO: {source['source_id']}")
    print(f"{'='*60}")
    
    gateway = FalGateway()
    
    try:
        # Step 1: Script
        print(f"\n  [1/5] Generating script...")
        script = generate_script(source)
        print(f"    Title: {script['title']}")
        script_path = WORKDIR / "script.json"
        with open(script_path, "w") as f:
            json.dump(script, f, indent=2)
        
        # Step 2: Storyboard
        print(f"  [2/5] Generating storyboard...")
        storyboard = generate_storyboard(script, source)
        sb_path = WORKDIR / "storyboard.json"
        with open(sb_path, "w") as f:
            json.dump(storyboard, f, indent=2)
        
        # Step 3: Images
        print(f"  [3/5] Generating images...")
        images = generate_images(storyboard, gateway)
        total_img_cost = sum(i["cost"] for i in images)
        print(f"    Images: {len(images)} | Cost: ${total_img_cost:.2f}")
        
        # Step 4: Audio
        print(f"  [4/5] Generating audio...")
        audio = generate_audio(script, gateway)
        total_audio_cost = sum(a["cost"] for a in audio)
        print(f"    Audio clips: {len(audio)} | Cost: ${total_audio_cost:.2f}")
        
        # Step 5: Assembly
        print(f"  [5/5] Assembling video...")
        output_path = WORKDIR / f"reel_{source['source_id']}.mp4"
        final_path = assemble_video(images, audio, script, str(output_path))
        print(f"    Video saved: {final_path}")
        
        # Upload to Drive (optional — warn but continue on auth failure)
        link = None
        try:
            print(f"  Uploading to Google Drive...")
            reel_factory_id = ensure_drive_folder("Reel_Factory")
            batch_folder_name = f"Single_{datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M')}"
            folder_id = ensure_drive_folder(batch_folder_name, parent_id=reel_factory_id)
            link, file_id = upload_to_drive(Path(final_path), folder_id)
            print(f"    Drive link: {link}")
        except Exception as drive_err:
            print(f"    WARNING: Google Drive upload failed: {drive_err}")
            print(f"    Video saved locally at: {final_path}")
        
        # Track
        save_used_items([source["source_id"]])
        
        # Summary
        print(f"\n{'='*60}")
        print("VIDEO COMPLETE")
        print(f"{'='*60}")
        print(f"  Title: {script['title']}")
        print(f"  Source: {source['source_id']}")
        if link:
            print(f"  Drive: {link}")
        print(f"  Local: {final_path}")
        print(f"  Total cost: ${total_img_cost + total_audio_cost:.2f}")
        
    except Exception as e:
        print(f"\n  ERROR: {e}")
        raise

if __name__ == "__main__":
    main()
