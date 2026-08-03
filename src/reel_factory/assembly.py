"""
Deterministic video assembly: static frames + per-scene audio alignment + bg music.

v2 approach:
  1. For each scene: loop the static image for the audio's duration → video segment
  2. Concatenate all segments + end card
  3. Add background music at very low volume (8%)
"""
from __future__ import annotations

import subprocess
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional

from reel_factory.models import (
    GeneratedImageAsset, GeneratedAudioAsset, ScriptPackage, StoryboardPackage,
)


# ── Cross-platform font resolution ─────────────────────────

_FONT_CANDIDATES = [
    # Linux (DejaVu)
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    # macOS system fonts
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    # Homebrew Linux-style paths on macOS
    "/opt/homebrew/share/fonts/dejavu-fonts-ttf-2.37/ttf/DejaVuSans-Bold.ttf",
    # Windows
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


def _find_font(bold: bool = True) -> Optional[str]:
    """Find a usable system font for text overlays. Cross-platform."""
    # Try candidates in order — bold first if requested
    candidates = _FONT_CANDIDATES if bold else list(reversed(_FONT_CANDIDATES))
    for path in candidates:
        if Path(path).exists():
            return path
    return None


def _get_font(size: int, bold: bool = True):
    """Load a font at the given size, falling back to Pillow default."""
    from PIL import ImageFont

    font_path = _find_font(bold=bold)
    if font_path:
        try:
            return ImageFont.truetype(font_path, size)
        except Exception:
            pass
    return ImageFont.load_default()


class AssemblyPipeline:
    """Assembles the final video from static images + per-scene audio."""

    def __init__(self, workdir: str | Path):
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.overlays_dir = self.workdir / "overlays"
        self.overlays_dir.mkdir(parents=True, exist_ok=True)

    # ── Text overlay helpers ───────────────────────────────────

    def _render_text_overlay(
        self,
        text: str,
        width: int = 1080,
        height: int = 1920,
        bg_alpha: int = 160,
    ) -> Path:
        """Render a semi-transparent text overlay PNG using Pillow."""
        from PIL import Image, ImageDraw

        base = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(base)

        band_top = int(height * 0.62)
        band_bottom = int(height * 0.92)
        draw.rectangle(
            [(0, band_top), (width, band_bottom)],
            fill=(0, 0, 0, bg_alpha),
        )

        font = _get_font(56, bold=True)

        max_chars_per_line = 22
        words = text.split()
        lines: List[str] = []
        current = ""
        for w in words:
            candidate = f"{current} {w}".strip()
            if len(candidate) <= max_chars_per_line:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = w
        if current:
            lines.append(current)
        lines = lines[:4]

        line_spacing = 12
        line_heights = []
        for ln in lines:
            try:
                bbox = draw.textbbox((0, 0), ln, font=font)
                line_heights.append(bbox[3] - bbox[1])
            except Exception:
                line_heights.append(56)
        total_text_h = sum(line_heights) + line_spacing * (len(lines) - 1)
        y = band_top + (band_bottom - band_top - total_text_h) // 2

        for ln in lines:
            try:
                bbox = draw.textbbox((0, 0), ln, font=font)
                tw = bbox[2] - bbox[0]
            except Exception:
                tw = 56 * len(ln) // 2
            x = (width - tw) // 2
            draw.text((x + 2, y + 2), ln, fill=(0, 0, 0, 200), font=font)
            draw.text((x, y), ln, fill=(255, 255, 255, 255), font=font)
            y += (line_heights[0] if line_heights else 56) + line_spacing

        out_path = self.overlays_dir / f"overlay_{abs(hash(text)) % 1000000}.png"
        base.save(out_path, "PNG")
        return out_path

    def _burn_overlay_ffmpeg(
        self,
        clip_path: str,
        overlay_png: Path,
        scene_id: str,
    ) -> str:
        """Burn a PNG overlay into a video clip using FFmpeg."""
        out_path = self.workdir / f"scene_overlay_{scene_id}.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-i", clip_path,
            "-i", str(overlay_png),
            "-filter_complex",
            "[0:v][1:v]overlay=0:0:format=auto[s];"
            "[s]scale=1080:1920:force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2[v]",
            "-map", "[v]",
            "-map", "0:a?",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-r", "30",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-shortest",
            str(out_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            print(f"  Overlay burn failed for {scene_id}: {result.stderr[:200]}")
            return clip_path
        return str(out_path)

    def _create_end_card(
        self,
        source_credit: str,
        duration: float = 3.0,
    ) -> str:
        """Create a simple end-card clip showing the source credit."""
        from PIL import Image, ImageDraw

        width, height = 1080, 1920
        img = Image.new("RGB", (width, height), (10, 10, 20))
        draw = ImageDraw.Draw(img)

        font = _get_font(64, bold=True)

        max_chars = 24
        words = source_credit.split()
        lines = []
        current = ""
        for w in words:
            candidate = f"{current} {w}".strip()
            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = w
        if current:
            lines.append(current)
        lines = lines[:5]

        line_spacing = 16
        line_heights = []
        for ln in lines:
            try:
                bbox = draw.textbbox((0, 0), ln, font=font)
                line_heights.append(bbox[3] - bbox[1])
            except Exception:
                line_heights.append(64)
        total_h = sum(line_heights) + line_spacing * (len(lines) - 1)
        y = (height - total_h) // 2

        for ln in lines:
            try:
                bbox = draw.textbbox((0, 0), ln, font=font)
                tw = bbox[2] - bbox[0]
            except Exception:
                tw = 64 * len(ln) // 2
            x = (width - tw) // 2
            draw.text((x, y), ln, fill=(255, 215, 0, 255), font=font)
            y += (line_heights[0] if line_heights else 64) + line_spacing

        small_font = _get_font(40, bold=False)
        sub_text = "Subscribe for more wisdom"
        try:
            bbox = draw.textbbox((0, 0), sub_text, font=small_font)
            tw = bbox[2] - bbox[0]
        except Exception:
            tw = 200
        draw.text(
            ((width - tw) // 2, y + 60),
            sub_text,
            fill=(200, 200, 200, 255),
            font=small_font,
        )

        endcard_png = self.workdir / "endcard.png"
        img.save(endcard_png, "PNG")

        endcard_mp4 = self.workdir / "endcard.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", str(endcard_png),
            "-f", "lavfi",
            "-i", "anullsrc=channel_layout=mono:sample_rate=24000",
            "-t", str(duration),
            "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
            "-r", "30",
            "-c:v", "libx264",
            "-tune", "stillimage",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-ar", "24000",
            "-ac", "1",
            "-b:a", "128k",
            "-shortest",
            str(endcard_mp4),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(f"End card creation failed: {result.stderr[:300]}")
        return str(endcard_mp4)

    def _get_local_image(self, image: GeneratedImageAsset) -> Optional[str]:
        """Download image to local file if needed, return local path."""
        if image.local_path and Path(image.local_path).exists():
            return image.local_path
        if image.output_url:
            tmp = self.workdir / f"image_{image.scene_id}.png"
            if tmp.exists():
                return str(tmp)
            try:
                urllib.request.urlretrieve(image.output_url, tmp)
                return str(tmp)
            except Exception:
                return None
        return None

    def _get_local_audio(self, audio: GeneratedAudioAsset) -> Optional[str]:
        """Get a local file path for an audio asset, downloading if necessary."""
        if audio.local_path and Path(audio.local_path).exists():
            return audio.local_path
        if audio.output_url:
            # Try common extensions
            for ext in (".mp3", ".wav"):
                tmp = self.workdir / f"narration_{audio.scene_id}{ext}"
                if tmp.exists():
                    return str(tmp)
            tmp = self.workdir / f"narration_{audio.scene_id}.mp3"
            try:
                urllib.request.urlretrieve(audio.output_url, tmp)
                return str(tmp)
            except Exception:
                return None
        return None

    def _create_scene_segment(
        self,
        image_path: str,
        audio_path: str,
        scene_id: str,
    ) -> str:
        """Create a video segment from a static image + narration audio.

        The image is looped for the duration of the audio (audio is timing master).
        """
        out_path = self.workdir / f"scene_{scene_id}.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", image_path,
            "-i", audio_path,
            "-c:v", "libx264",
            "-tune", "stillimage",
            "-pix_fmt", "yuv420p",
            "-r", "30",
            "-preset", "fast",
            "-crf", "23",
            "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,"
                   "pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
            "-c:a", "aac",
            "-b:a", "128k",
            "-shortest",
            str(out_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(
                f"Scene segment creation failed for {scene_id}: {result.stderr[:300]}"
            )
        return str(out_path)

    # ── Main assembly ──────────────────────────────────────────

    def assemble(
        self,
        images: List[GeneratedImageAsset],
        script: ScriptPackage,
        narration: Optional[List[GeneratedAudioAsset]] = None,
        storyboard: Optional[StoryboardPackage] = None,
        output_path: Optional[str] = None,
    ) -> str:
        """
        Assemble the final video using FFmpeg with static frames + audio alignment.

        For each scene:
          1. Download image locally
          2. Match with per-scene narration audio
          3. Create video segment (static image looped for audio duration)
        Then concatenate all segments + end card, add background music at 8%.
        """
        if output_path is None:
            output_path = str(self.workdir / "final_reel.mp4")

        audio_map: Dict[str, GeneratedAudioAsset] = {}
        if narration:
            for a in narration:
                if a.scene_id:
                    audio_map[a.scene_id] = a

        # ── Step 1: Create per-scene video segments ───────────────
        processed_segments: List[str] = []
        for image in images:
            local_image = self._get_local_image(image)
            if not local_image:
                print(f"  Skipping {image.scene_id}: no image available")
                continue

            scene_audio = audio_map.get(image.scene_id)
            local_audio = self._get_local_audio(scene_audio) if scene_audio else None

            scene_id = image.scene_id

            if local_audio:
                print(f"  Creating segment for {scene_id} (image + audio)...")
                segment = self._create_scene_segment(local_image, local_audio, scene_id)
            else:
                # No audio — create a 5s silent segment from the image
                print(f"  Creating segment for {scene_id} (image only, no audio)...")
                segment = self._create_silent_segment(local_image, scene_id, duration=5.0)

            processed_segments.append(segment)

        if not processed_segments:
            raise RuntimeError("No segments available for assembly")

        # ── Step 2: Create end card ────────────────────────────────
        print(f"  Creating end card: '{script.source_credit}'")
        endcard_path = self._create_end_card(script.source_credit, duration=3.0)
        processed_segments.append(endcard_path)

        # ── Step 3: Concatenate all segments using the concat filter ──
        # The concat filter handles format normalization automatically,
        # avoiding the audio duration skew that the concat demuxer causes
        # when segments have different sample rates or channel layouts.
        num_segments = len(processed_segments)
        concat_inputs = []
        for seg_path in processed_segments:
            safe = seg_path.replace("'", r"'\''")
            concat_inputs.extend(["-i", safe])

        filter_inputs = "".join(
            f"[{i}:v][{i}:a]" for i in range(num_segments)
        )
        video_concat_path = self.workdir / "video_concat.mp4"
        concat_cmd = [
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
            str(video_concat_path),
        ]
        print(f"  Concatenating {len(processed_segments)} segments...")
        result = subprocess.run(concat_cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg concat failed: {result.stderr[:500]}")

        # Get total video duration for background music
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(video_concat_path)],
            capture_output=True, text=True, timeout=30
        )
        video_duration = 30.0
        if probe.returncode == 0:
            import json
            fmt = json.loads(probe.stdout).get("format", {})
            video_duration = float(fmt.get("duration", 30.0))

        # ── Step 4: Generate + add background music at 8% volume ───
        music_tmp = self.workdir / "bg_music.mp3"
        if not music_tmp.exists():
            print(f"  Generating background music ({video_duration:.0f}s)...")
            music_cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", f"sine=frequency=220:duration={video_duration:.1f}",
                "-f", "lavfi",
                "-i", f"sine=frequency=330:duration={video_duration:.1f}",
                "-filter_complex",
                "[0:a]volume=0.3[a1];"
                "[1:a]volume=0.15[a2];"
                "[a1][a2]amix=inputs=2:duration=longest,"
                "lowpass=f=800,"
                "aecho=0.8:0.7:60:0.3,"
                "volume=0.5[mix]",
                "-map", "[mix]",
                "-c:a", "libmp3lame",
                "-b:a", "96k",
                str(music_tmp),
            ]
            subprocess.run(music_cmd, capture_output=True, text=True, timeout=60)

        if music_tmp.exists():
            mux_cmd = [
                "ffmpeg", "-y",
                "-i", str(video_concat_path),
                "-i", str(music_tmp),
                "-filter_complex",
                "[1:a]volume=0.08[bg];"
                "[0:a][bg]amix=inputs=2:duration=first:dropout_transition=0[aout]",
                "-map", "0:v",
                "-map", "[aout]",
                "-c:v", "copy",
                "-c:a", "aac",
                "-ar", "24000",
                "-ac", "1",
                "-b:a", "128k",
                "-shortest",
                str(output_path),
            ]
            print(f"  Adding background music at 8% volume...")
            result = subprocess.run(mux_cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                raise RuntimeError(f"FFmpeg music mix failed: {result.stderr[:500]}")
        else:
            import shutil
            shutil.copy(str(video_concat_path), output_path)

        print(f"  Final reel: {output_path}")
        return output_path

    def _create_silent_segment(
        self, image_path: str, scene_id: str, duration: float = 5.0
    ) -> str:
        """Create a silent video segment from a static image."""
        out_path = self.workdir / f"scene_{scene_id}.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", image_path,
            "-f", "lavfi",
            "-i", "anullsrc=channel_layout=mono:sample_rate=24000",
            "-t", str(duration),
            "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,"
                   "pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
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
            str(out_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(
                f"Silent segment failed for {scene_id}: {result.stderr[:300]}"
            )
        return str(out_path)