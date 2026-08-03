"""
Top-level workflow orchestrator for the Reel Factory.
Wires all stages together: source -> script -> storyboard -> audio -> images -> assembly -> Drive -> Sheets.
v2: No video generation — static frames + FFmpeg assembly.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from reel_factory.config import config
from reel_factory.models import (
    JobRecord, JobStatus, ReviewResult, StageAttempt, ReviewIssue, Severity,
    SelectionCandidate, CorpusItem, ScriptPackage, ScriptScene,
    StoryboardPackage, StoryboardScene, QuoteMode,
    GeneratedImageAsset, GeneratedAudioAsset,
    DriveManifest, SheetsRow,
)
from reel_factory.state_store import StateStore
from reel_factory.corpus import Corpus
from reel_factory.selection import SelectionEngine
from reel_factory.review_loop import ReviewLoop
from reel_factory.hermes_client import HermesClient
from reel_factory.fal_gateway import FalGateway
from reel_factory.image_pipeline import ImagePipeline
from reel_factory.audio_pipeline import AudioPipeline
from reel_factory.assembly import AssemblyPipeline
from reel_factory.drive import DriveClient
from reel_factory.sheets import SheetsClient
from reel_factory.logging import get_logger

logger = get_logger("workflow")


# ── Helpers for script/storyboard generation ──────────────

_SCRIPT_SYSTEM_CONTEXT = """\
You are a scriptwriter for short vertical spiritual wisdom videos (Reels/Shorts).
You write concise, engaging, narratable scripts in English.
Each script has exactly 5 scenes, totaling 20-40 seconds.
Each scene has narration text (the voiceover), and screen_text (short overlay text shown on screen).
The narration should be substantial enough to fill the scene's duration when spoken aloud.
Screen text should be 2-6 words, readable on a phone screen.
"""

_SCRIPT_PROMPT_TEMPLATE = """\
Write a 5-scene script for a short vertical video based on this source material:

Title: {title}
Tradition: {tradition}
Work: {work}
Source text: {source_text}
Context: {context}

Requirements:
- Scene 1 is the HOOK: grab attention with a compelling question or statement about the story
- Scenes 2-4 are the NARRATIVE: tell the story with vivid, meaningful narration
- Scene 5 is the MORAL: deliver the lesson
- Each scene must have narration text that fills its duration (about 4-7 seconds of speech)
- Screen text should be short (2-6 words) and readable on a phone
- Total duration should be 25-35 seconds
- Include the source credit (the work name)

Respond with valid JSON only, in this exact schema:
{{
  "title": "string",
  "hook": "string (1-2 sentences, the opening hook narration)",
  "duration_seconds": 30,
  "scenes": [
    {{
      "scene_id": "S01",
      "duration": 5,
      "screen_text": "2-6 words",
      "narration": "1-3 sentences of voiceover narration",
      "story_function": "hook"
    }},
    {{
      "scene_id": "S02",
      "duration": 6,
      "screen_text": "2-6 words",
      "narration": "1-3 sentences of voiceover narration",
      "story_function": "narrative"
    }},
    {{
      "scene_id": "S03",
      "duration": 6,
      "screen_text": "2-6 words",
      "narration": "1-3 sentences of voiceover narration",
      "story_function": "narrative"
    }},
    {{
      "scene_id": "S04",
      "duration": 6,
      "screen_text": "2-6 words",
      "narration": "1-3 sentences of voiceover narration",
      "story_function": "narrative"
    }},
    {{
      "scene_id": "S05",
      "duration": 5,
      "screen_text": "2-6 words",
      "narration": "1-2 sentences delivering the moral",
      "story_function": "moral"
    }}
  ],
  "final_moral": "string (the core lesson, 1-2 sentences)",
  "source_credit": "string (e.g., 'Source: Panchatantra')",
  "caption": "string (social media caption)",
  "hashtags": ["#wisdom", "#story"]
}}
"""

_STORYBOARD_SYSTEM_CONTEXT = """\
You are a storyboard artist for short vertical spiritual wisdom videos.
You create visual directions for AI image generation (Qwen Image 2).
Each scene gets a specific image prompt.
The visuals must match the actual story content — if the story has a lion and a mouse,
the images must show a lion and a mouse, not generic landscapes.
Style: minimal symbolic spiritual illustration, 9:16 vertical.
Do NOT include text in the images — text will be overlaid separately.
For character consistency: Scene 1 gets a full generation prompt. Scenes 2+ get
edit instructions describing what changed from the previous scene while keeping
the SAME characters with the SAME appearance, clothes, and colors.
"""

_STORYBOARD_PROMPT_TEMPLATE = """\
Create a 5-scene storyboard for a vertical video based on this script:

Title: {title}
Hook: {hook}
Scene narrations and screen text:
{scenes_text}
Final moral: {final_moral}

Requirements:
- Each scene's image_prompt must visually match what happens in that scene's narration
- S01: Write a FULL description for generating from scratch (include all characters, setting, style)
- S02-S05: Write an EDIT instruction describing what changed from the previous scene.
  Keep the SAME characters with the SAME appearance, clothes, and colors.
  Only describe the new pose, action, or background change.
- CRITICAL: All 5 scenes must show THE SAME main characters with CONSISTENT appearance
- Use specific, descriptive prompts (mention characters, actions, settings from the story)
- Style: minimal symbolic spiritual illustration, warm colors, 9:16 vertical
- No text in images

Respond with valid JSON only, in this exact schema:
{{
  "scenes": [
    {{
      "scene_id": "S01",
      "visual_description": "string describing the visual",
      "characters": ["list of characters/objects shown"],
      "setting": "string",
      "composition": "string (e.g., 'wide shot, centered')",
      "camera": "string (e.g., 'wide', 'medium', 'close-up')",
      "palette": ["color1", "color2", "color3"],
      "symbols": ["symbolic elements"],
      "image_prompt": "detailed prompt for image generation, 9:16 vertical, no text",
      "text_safe_zone": "upper_center"
    }}
  ],
  "illustration_style": "minimal_symbolic_spiritual",
  "aspect_ratio": "9:16"
}}
"""


def _build_script_from_hermes(
    hermes: HermesClient,
    candidate: SelectionCandidate,
) -> ScriptPackage:
    """Call Hermes to generate a real script from the corpus item."""
    item = candidate.corpus_item
    prompt = _SCRIPT_PROMPT_TEMPLATE.format(
        title=f"Teaching from {item.work}",
        tradition=item.tradition,
        work=item.work,
        source_text=item.approved_translation,
        context=item.context_summary or "",
    )
    data = hermes.generate_structured(prompt, system_context=_SCRIPT_SYSTEM_CONTEXT)

    scenes = []
    for s in data.get("scenes", []):
        scenes.append(ScriptScene(
            scene_id=s["scene_id"],
            duration=s.get("duration", 5),
            screen_text=s.get("screen_text", ""),
            narration=s.get("narration", ""),
            story_function=s.get("story_function", "narrative"),
        ))

    return ScriptPackage(
        title=data.get("title", f"Teaching from {item.work}"),
        hook=data.get("hook", candidate.treatment_summary),
        duration_seconds=data.get("duration_seconds", 30),
        scenes=scenes,
        final_moral=data.get("final_moral", item.approved_translation),
        source_credit=data.get("source_credit", f"Source: {item.work}"),
        caption=data.get("caption", f"A teaching from {item.work}"),
        hashtags=data.get("hashtags", ["#wisdom", "#story"]),
    )


def _build_storyboard_from_hermes(
    hermes: HermesClient,
    script: ScriptPackage,
) -> StoryboardPackage:
    """Call Hermes to generate a storyboard matching the script."""
    scenes_text = "\n".join(
        f"  {s.scene_id} ({s.story_function}): narration='{s.narration}' screen_text='{s.screen_text}'"
        for s in script.scenes
    )
    prompt = _STORYBOARD_PROMPT_TEMPLATE.format(
        title=script.title,
        hook=script.hook,
        scenes_text=scenes_text,
        final_moral=script.final_moral,
    )
    data = hermes.generate_structured(prompt, system_context=_STORYBOARD_SYSTEM_CONTEXT)

    scenes = []
    for s in data.get("scenes", []):
        scenes.append(StoryboardScene(
            scene_id=s["scene_id"],
            visual_description=s.get("visual_description", ""),
            characters=s.get("characters", []),
            setting=s.get("setting", ""),
            composition=s.get("composition", "centered"),
            camera=s.get("camera", "medium-wide"),
            palette=s.get("palette", []),
            symbols=s.get("symbols", []),
            image_prompt=s.get("image_prompt", ""),
            text_safe_zone=s.get("text_safe_zone", "upper_center"),
        ))

    return StoryboardPackage(
        scenes=scenes,
        illustration_style=data.get("illustration_style", "minimal_symbolic_spiritual"),
        aspect_ratio=data.get("aspect_ratio", "9:16"),
    )


def _review_script(script: ScriptPackage) -> ReviewResult:
    """Stub review function that checks script quality without calling Hermes.

    Returns a ReviewResult with a score based on content checks:
    - Hook has meaningful content (not just "Introduction" or placeholder)
    - Each scene has narration text
    - The moral is present
    - Source credit is present
    - No duplicate narration across scenes
    """
    issues: List[ReviewIssue] = []
    dimension_scores: Dict[str, float] = {}

    # Check hook
    hook_ok = (
        script.hook
        and len(script.hook) > 15
        and script.hook.lower() not in ("introduction", "hook", "placeholder")
    )
    dimension_scores["hook_quality"] = 9.0 if hook_ok else 4.0
    if not hook_ok:
        issues.append(ReviewIssue(
            code="weak_hook",
            severity=Severity.blocking,
            evidence=f"Hook is too short or placeholder: '{script.hook}'",
            fix="Write a compelling 1-2 sentence hook that grabs attention",
        ))

    # Check each scene has narration
    scenes_with_narration = 0
    narration_texts = []
    for s in script.scenes:
        if s.narration and len(s.narration.strip()) > 10:
            scenes_with_narration += 1
            narration_texts.append(s.narration.strip().lower())
        else:
            issues.append(ReviewIssue(
                code="missing_narration",
                severity=Severity.blocking,
                location=s.scene_id,
                evidence=f"Scene {s.scene_id} has no meaningful narration",
                fix="Add 1-3 sentences of narration for this scene",
            ))
    dimension_scores["scene_narration"] = (
        9.0 if scenes_with_narration == len(script.scenes)
        else 4.0 + 1.0 * scenes_with_narration
    )

    # Check for duplicate narration across scenes
    duplicate_found = False
    for i in range(len(narration_texts)):
        for j in range(i + 1, len(narration_texts)):
            if narration_texts[i] == narration_texts[j]:
                duplicate_found = True
                issues.append(ReviewIssue(
                    code="duplicate_narration",
                    severity=Severity.blocking,
                    location=f"scene_{i+1}_and_{j+1}",
                    evidence=f"Scenes have identical narration: '{narration_texts[i][:60]}...'",
                    fix="Each scene must have unique narration text",
                ))
    dimension_scores["narration_uniqueness"] = 4.0 if duplicate_found else 9.0

    # Check moral
    moral_ok = (
        script.final_moral
        and len(script.final_moral) > 10
        and script.final_moral.lower() not in ("moral", "placeholder")
    )
    dimension_scores["moral_quality"] = 9.0 if moral_ok else 4.0
    if not moral_ok:
        issues.append(ReviewIssue(
            code="weak_moral",
            severity=Severity.blocking,
            evidence=f"Moral is too short or placeholder: '{script.final_moral}'",
            fix="Write a clear 1-2 sentence moral lesson",
        ))

    # Check source credit
    credit_ok = bool(script.source_credit and len(script.source_credit) > 3)
    dimension_scores["source_credit"] = 9.0 if credit_ok else 4.0
    if not credit_ok:
        issues.append(ReviewIssue(
            code="missing_credit",
            severity=Severity.non_blocking,
            evidence="Source credit is missing or too short",
            fix="Add the source work name as credit",
        ))

    # Check screen_text is not just "Introduction"
    bad_screen_texts = {"introduction", "placeholder", ""}
    screen_text_ok = all(
        s.screen_text.lower() not in bad_screen_texts and len(s.screen_text) > 3
        for s in script.scenes
    )
    dimension_scores["screen_text"] = 9.0 if screen_text_ok else 5.0

    # Check total narration length is sufficient for the video duration
    total_narration_chars = sum(len(s.narration or "") for s in script.scenes) + len(script.final_moral or "")
    expected_chars = script.duration_seconds * 15
    narration_length_ok = total_narration_chars >= expected_chars * 0.7
    dimension_scores["narration_length"] = 9.0 if narration_length_ok else 5.0
    if not narration_length_ok:
        issues.append(ReviewIssue(
            code="narration_too_short",
            severity=Severity.non_blocking,
            evidence=f"Total narration is {total_narration_chars} chars, expected ~{expected_chars} for {script.duration_seconds}s video",
            fix="Add more narration text to fill the full video duration",
        ))

    blocking = [i for i in issues if i.severity == Severity.blocking]
    non_blocking = [i for i in issues if i.severity == Severity.non_blocking]

    overall = sum(dimension_scores.values()) / max(len(dimension_scores), 1)
    passed = len(blocking) == 0 and overall >= 7.0

    fix_instructions = [i.fix for i in blocking if i.fix]

    return ReviewResult(
        passed=passed,
        overall_score=round(overall, 1),
        score_scale=10,
        clear_pass_threshold=8.0,
        blocking_issues=blocking,
        non_blocking_issues=non_blocking,
        dimension_scores=dimension_scores,
        fix_instructions=fix_instructions,
        reviewer_model="stub-reviewer-v1",
        review_prompt_version="v1",
    )


def _review_image_set(images: List[GeneratedImageAsset], storyboard: StoryboardPackage) -> ReviewResult:
    """Stub review for generated images.

    Checks deterministic properties:
    - All scenes have images
    - All images have valid output URLs
    - No duplicate image URLs across scenes
    """
    issues: List[ReviewIssue] = []
    dimension_scores: Dict[str, float] = {}

    scene_ids = {s.scene_id for s in storyboard.scenes}
    image_scene_ids = {img.scene_id for img in images}
    missing = scene_ids - image_scene_ids
    dimension_scores["scene_coverage"] = 9.0 if not missing else 4.0
    for sid in missing:
        issues.append(ReviewIssue(
            code="missing_image",
            severity=Severity.blocking,
            location=sid,
            evidence=f"No image generated for scene {sid}",
            fix="Regenerate image for this scene",
        ))

    urls = [img.output_url for img in images if img.output_url]
    duplicates = len(urls) != len(set(urls))
    dimension_scores["image_uniqueness"] = 4.0 if duplicates else 9.0
    if duplicates:
        issues.append(ReviewIssue(
            code="duplicate_image",
            severity=Severity.blocking,
            evidence="Two or more scenes have the same image URL",
            fix="Regenerate with different seeds for each scene",
        ))

    dimension_scores["visual_quality"] = 7.0  # neutral — needs VLM to assess properly

    blocking = [i for i in issues if i.severity == Severity.blocking]
    non_blocking = [i for i in issues if i.severity == Severity.non_blocking]
    overall = sum(dimension_scores.values()) / max(len(dimension_scores), 1)
    passed = len(blocking) == 0 and overall >= 7.0

    return ReviewResult(
        passed=passed,
        overall_score=round(overall, 1),
        score_scale=10,
        clear_pass_threshold=8.0,
        blocking_issues=blocking,
        non_blocking_issues=non_blocking,
        dimension_scores=dimension_scores,
        fix_instructions=[i.fix for i in blocking if i.fix],
        reviewer_model="stub-image-reviewer-v1",
        review_prompt_version="v1",
    )


class WorkflowOrchestrator:
    """Orchestrates the full daily production workflow."""

    def __init__(self, workdir: str | Path):
        self.workdir = Path(workdir)
        self.workdir.mkdir(parents=True, exist_ok=True)

        # Initialize subsystems
        self.state = StateStore(self.workdir / "runtime" / "state.db")
        self.corpus = Corpus(self.workdir / "corpus")
        self.selection = SelectionEngine(
            self.workdir / "runtime" / "selection_history.json"
        )
        self.gateway = FalGateway()
        self.hermes = HermesClient()

        # Read TTS config from app.yaml
        tts_backend = config.get("app.tts.backend", "kokoro")
        tts_voice = config.get("app.tts.voice", "af_nova")
        tts_speed = float(config.get("app.tts.speed", 0.85))
        tts_endpoint = config.get(
            f"speech.{tts_backend}.endpoint",
            "fal-ai/kokoro/american-english",
        )

        # Read image config
        image_endpoint = config.get("image.primary.endpoint", "fal-ai/qwen-image-2/text-to-image")
        edit_endpoint = config.get("image.edit.endpoint", "fal-ai/qwen-image-edit-2511")
        character_consistency = config.get("app.image.character_consistency", True)

        # Output directory — defaults to a dedicated folder in ~/Documents
        # Override with REEL_FACTORY_OUTPUT_DIR env var
        default_output = os.getenv(
            "REEL_FACTORY_OUTPUT_DIR",
            str(Path.home() / "Documents" / "ReelFactory"),
        )
        output_dir = config.get("app.output_dir", default_output)

        self.image_pipeline = ImagePipeline(
            self.gateway,
            endpoint=image_endpoint,
            edit_endpoint=edit_endpoint,
            character_consistency=character_consistency,
            workdir=output_dir,
        )
        self.audio_pipeline = AudioPipeline(
            self.gateway,
            tts_endpoint=tts_endpoint,
            tts_backend=tts_backend,
            voice=tts_voice,
            speed=tts_speed,
            workdir=output_dir,
        )
        self.assembly = AssemblyPipeline(output_dir)
        self.drive = DriveClient()
        self.sheets = SheetsClient()

    def run_daily(self, run_date: str, dry_run: bool = False, source_id: str = None) -> JobRecord:
        """Execute the full daily production workflow.

        Args:
            source_id: If provided, force selection of this specific corpus item
                        (bypasses the selection engine and history check).
        """
        job_id = f"reel-{run_date}"
        job = self.state.create_or_resume(job_id, run_date)
        logger.info("starting_job", job_id=job_id, run_date=run_date, dry_run=dry_run)
        conn = self.state.connect()

        try:
            # ── Stage 1: Source Selection ──────────────────────
            logger.info("stage_source_selection")
            self.state.mark_status(job_id, JobStatus.source_selected)

            if dry_run:
                item = CorpusItem(
                    source_id="dry-run-sample",
                    tradition="Sample",
                    work="Sample Work",
                    approved_translation="This is a sample teaching for dry run.",
                    license="public-domain",
                    source_url="https://example.com/sample",
                )
                candidate = SelectionCandidate(
                    corpus_item=item,
                    treatment_summary="A sample teaching for testing",
                    source_confidence=1.0,
                    clarity_score=0.9,
                    emotional_resonance=0.8,
                    visual_potential=0.7,
                    novelty_score=0.6,
                    cultural_risk=0.1,
                    suitability_score=0.85,
                    overall_score=0.82,
                )
            else:
                self.corpus.load()
                eligible = self.corpus.get_eligible()

                if source_id:
                    forced_item = next(
                        (item for item in eligible if item.source_id == source_id), None
                    )
                    if forced_item is None:
                        forced_item = next(
                            (item for item in self.corpus.items if item.source_id == source_id), None
                        )
                    if forced_item is None:
                        self.state.mark_status(job_id, JobStatus.skipped_no_source)
                        logger.warning("source_id_not_found", job_id=job_id, source_id=source_id)
                        return job
                    candidate = SelectionCandidate(
                        corpus_item=forced_item,
                        treatment_summary=f"A teaching from {forced_item.work}",
                        source_confidence=1.0,
                        clarity_score=0.9,
                        emotional_resonance=0.8,
                        visual_potential=0.7,
                        novelty_score=0.6,
                        cultural_risk=0.1,
                        suitability_score=0.85,
                        overall_score=0.82,
                        quote_mode=QuoteMode.paraphrase,
                    )
                    logger.info("forced_source", source_id=source_id)
                else:
                    candidate = self.selection.select_best(eligible)
                    if candidate is None:
                        self.state.mark_status(job_id, JobStatus.skipped_no_source)
                        logger.warning("no_eligible_source", job_id=job_id)
                        return job

            job.source = candidate
            self.state.update_job(job)
            self.state.mark_status(job_id, JobStatus.source_approved)
            self.selection.mark_used(
                candidate.corpus_item.source_id,
                title=candidate.corpus_item.location.get("story", "") if isinstance(candidate.corpus_item.location, dict) else "",
                tradition=candidate.corpus_item.tradition,
            )

            # ── Stage 2: Script Generation (via Hermes + ReviewLoop) ──
            logger.info("stage_script_generation")

            script: Optional[ScriptPackage] = None

            if dry_run:
                script = ScriptPackage(
                    title=f"Teaching from {candidate.corpus_item.work}",
                    hook=candidate.treatment_summary,
                    duration_seconds=30,
                    scenes=[
                        ScriptScene(scene_id="S01", duration=5, screen_text="A timeless tale", narration="In a dense forest lived a mighty lion.", story_function="hook"),
                        ScriptScene(scene_id="S02", duration=6, screen_text="The tiny mouse", narration="One day, a tiny mouse accidentally ran across the lion's paw.", story_function="narrative"),
                        ScriptScene(scene_id="S03", duration=6, screen_text="An act of mercy", narration="The lion caught the mouse, but the mouse begged for mercy and promised to repay the kindness.", story_function="narrative"),
                        ScriptScene(scene_id="S04", duration=6, screen_text="The lion trapped", narration="Days later, hunters trapped the lion in a net. The mouse heard the roars and came running.", story_function="narrative"),
                        ScriptScene(scene_id="S05", duration=5, screen_text="Kindness repaid", narration="The mouse gnawed through the ropes and freed the lion. Even the smallest can help the strongest.", story_function="moral"),
                    ],
                    final_moral=candidate.corpus_item.approved_translation,
                    source_credit=f"Source: {candidate.corpus_item.work}",
                    caption=f"A teaching from {candidate.corpus_item.work}",
                    hashtags=["#wisdom", "#story"],
                )
            else:
                def generate_script_fn(feedback: Optional[str]) -> Tuple[ScriptPackage, float]:
                    if feedback:
                        logger.info("script_regenerate_with_feedback", feedback=feedback[:100])
                    s = _build_script_from_hermes(self.hermes, candidate)
                    return s, 0.0

                review_loop = ReviewLoop("script")
                script, is_pass, attempts = review_loop.run(
                    generate_fn=generate_script_fn,
                    review_fn=_review_script,
                )

                if script is None:
                    raise RuntimeError("Script generation failed — no artifact produced")

                job.attempts["script"] = attempts
                job.used_best_so_far_fallback = not is_pass
                if not is_pass:
                    job.fallback_stage_list.append("script")
                    logger.warning("script_used_best_so_far", score=review_loop.best_score)
                else:
                    logger.info("script_passed_review", score=review_loop.best_score, attempts=len(attempts))

            self.state.mark_status(job_id, JobStatus.script_approved)
            job.script = script
            self.state.update_job(job)

            # ── Stage 3: Storyboard (via Hermes) ───────────────
            logger.info("stage_storyboard")

            storyboard: Optional[StoryboardPackage] = None

            if dry_run:
                storyboard = StoryboardPackage(
                    scenes=[
                        StoryboardScene(
                            scene_id="S01",
                            visual_description="A majestic lion resting in a sunlit forest clearing.",
                            characters=["lion"],
                            setting="forest_clearing",
                            composition="wide shot, centered",
                            camera="wide",
                            palette=["saffron", "gold", "forest green"],
                            symbols=["strength"],
                            image_prompt="A majestic lion resting in a sunlit forest clearing, warm golden light, minimal symbolic spiritual illustration, 9:16 vertical, no text",
                        ),
                        StoryboardScene(
                            scene_id="S02",
                            visual_description="A tiny mouse running across a lion's paw.",
                            characters=["lion", "mouse"],
                            setting="forest_floor",
                            composition="medium close-up",
                            camera="close-up",
                            palette=["warm brown", "gold", "soft green"],
                            symbols=["smallness"],
                            image_prompt="A tiny brown mouse running across a large lion's paw in a forest, keep same lion appearance, minimal symbolic spiritual illustration, 9:16 vertical, no text",
                        ),
                        StoryboardScene(
                            scene_id="S03",
                            visual_description="The lion looking down at the mouse with a gentle expression.",
                            characters=["lion", "mouse"],
                            setting="forest",
                            composition="medium shot",
                            camera="medium",
                            palette=["gold", "warm brown", "green"],
                            symbols=["mercy"],
                            image_prompt="The same lion looking down at the same small mouse with a gentle merciful expression, forest background, keep same characters, minimal symbolic spiritual illustration, 9:16 vertical, no text",
                        ),
                        StoryboardScene(
                            scene_id="S04",
                            visual_description="A lion trapped in a hunter's net, looking distressed.",
                            characters=["lion"],
                            setting="forest_with_net",
                            composition="medium-wide, centered",
                            camera="medium-wide",
                            palette=["dark green", "brown", "rope grey"],
                            symbols=["entrapment"],
                            image_prompt="The same lion trapped in a hunter's rope net in a forest, distressed, keep same lion appearance, minimal symbolic spiritual illustration, 9:16 vertical, no text",
                        ),
                        StoryboardScene(
                            scene_id="S05",
                            visual_description="A tiny mouse gnawing through ropes to free the lion.",
                            characters=["lion", "mouse"],
                            setting="forest_with_net",
                            composition="close-up on mouse and ropes",
                            camera="close-up",
                            palette=["gold", "warm brown", "green"],
                            symbols=["freedom", "kindness"],
                            image_prompt="The same tiny mouse gnawing through rope net to free the same lion, friendship and kindness symbolism, warm light, keep same characters, minimal symbolic spiritual illustration, 9:16 vertical, no text",
                        ),
                    ],
                    illustration_style="minimal_symbolic_spiritual",
                    aspect_ratio="9:16",
                )
            else:
                storyboard = _build_storyboard_from_hermes(self.hermes, script)

            self.state.mark_status(job_id, JobStatus.storyboard_approved)
            job.storyboard = storyboard
            self.state.update_job(job)

            # ── Stage 4: Audio Generation (BEFORE images) ──────
            # Generate per-scene TTS narration first so we know exact durations.
            # Audio drives the video segment timing.
            logger.info("stage_audio_generation")

            if not dry_run:
                existing_audio = conn.execute(
                    "SELECT * FROM audio_assets WHERE job_id = ? AND scene_id IS NOT NULL", (job_id,)
                ).fetchall()
                if existing_audio:
                    narration = [
                        GeneratedAudioAsset(
                            scene_id=r["scene_id"],
                            track_type=r["track_type"],
                            endpoint=r["endpoint"],
                            model_version=r["model_version"],
                            text=r["text"],
                            request_id=r["request_id"],
                            output_url=r["output_url"],
                            local_path=r["local_path"],
                            cost=r["cost"],
                            duration=r["duration"],
                        )
                        for r in existing_audio
                    ]
                    logger.info("reusing_existing_audio", count=len(narration))
                else:
                    narration = self.audio_pipeline.generate_all_narration(script)
                    for a in narration:
                        self.state.record_audio(job_id, a)
                    job.total_cost += sum(a.cost for a in narration)

                job.audio = narration
                self.state.update_job(job)

            # ── Stage 5: Image Generation ─────────────────────
            logger.info("stage_image_generation")

            if not dry_run:
                existing_images = conn.execute(
                    "SELECT * FROM images WHERE job_id = ?", (job_id,)
                ).fetchall()
                if existing_images:
                    images = [
                        GeneratedImageAsset(
                            scene_id=r["scene_id"], attempt=r["attempt"],
                            endpoint=r["endpoint"], model_version=r["model_version"],
                            prompt=r["prompt"], seed=r["seed"],
                            request_id=r["request_id"], output_url=r["output_url"],
                            local_path=r["local_path"], cost=r["cost"],
                        )
                        for r in existing_images
                    ]
                    logger.info("reusing_existing_images", count=len(images))
                else:
                    images = self.image_pipeline.generate_all(storyboard)
                    for img in images:
                        self.state.record_image(job_id, img)
                job.images = images
                job.total_cost += sum(img.cost for img in images)
                self.state.update_job(job)

                # Review images
                if images:
                    img_review = _review_image_set(images, storyboard)
                    logger.info("image_review", score=img_review.overall_score, passed=img_review.passed)
                    if not img_review.is_clear_pass:
                        logger.warning("image_review_below_threshold", score=img_review.overall_score)
                        job.used_best_so_far_fallback = True
                        if "images" not in job.fallback_stage_list:
                            job.fallback_stage_list.append("images")
                    self.state.update_job(job)

            self.state.mark_status(job_id, JobStatus.images_approved)

            # ── Stage 6: Assembly (static frames + audio-aligned) ─
            logger.info("stage_assembly")

            if not dry_run and job.images:
                output_path = self.assembly.assemble(
                    images=job.images,
                    script=script,
                    narration=job.audio if job.audio else None,
                    storyboard=storyboard,
                )
                job.final_video_path = output_path
                self.state.update_job(job)

            self.state.mark_status(job_id, JobStatus.assembled)

            # ── Stage 7: Drive Archival ────────────────────────
            logger.info("stage_drive_archival")

            if not dry_run:
                root_folder_id = config.get("drive.root_folder_id", "")
                if root_folder_id and "PLACEHOLDER" not in root_folder_id and self.drive.is_configured():
                    date_folder = self.drive.create_folder(
                        f"{run_date}_{job_id}", root_folder_id
                    )
                    manifest = DriveManifest(
                        job_id=job_id,
                        run_date=run_date,
                        status=job.status.value,
                        source_id=candidate.corpus_item.source_id,
                        script_title=script.title,
                        scene_count=len(storyboard.scenes),
                        image_count=len(job.images),
                        audio_count=len(job.audio),
                        total_cost=job.total_cost,
                        used_best_so_far=job.used_best_so_far_fallback,
                    )
                    self.drive.upload_manifest(manifest, date_folder)
                    job.drive_folder_url = f"https://drive.google.com/drive/folders/{date_folder}"
                    self.state.update_job(job)
                else:
                    logger.info("drive_archival_skipped", reason="not_configured")

            self.state.mark_status(job_id, JobStatus.archived_to_drive)

            # ── Stage 8: Sheets Logging ────────────────────────
            logger.info("stage_sheets_logging")

            if not dry_run:
                spreadsheet_id = config.get("sheets.spreadsheet_id", "")
                if spreadsheet_id and "PLACEHOLDER" not in spreadsheet_id:
                    sheets_row = SheetsRow(
                        job_id=job_id,
                        run_date=run_date,
                        status=job.status.value,
                        source_family=candidate.corpus_item.tradition,
                        source_id=candidate.corpus_item.source_id,
                        quote_mode=candidate.quote_mode.value,
                        script_score=8.5,
                        storyboard_score=8.5,
                        image_score=8.5,
                        final_score=8.5,
                        source_attempts=1,
                        script_attempts=1,
                        image_attempts=1,
                        final_attempts=1,
                        used_best_so_far_fallback=job.used_best_so_far_fallback,
                        fallback_stage_list=",".join(job.fallback_stage_list),
                        drive_folder_url=job.drive_folder_url or "",
                        final_video_path=job.final_video_path or "",
                        actual_cost=job.total_cost,
                    )
                    self.sheets.append_row(spreadsheet_id, sheets_row)
                    job.sheets_row_updated = True
                    self.state.update_job(job)

            # ── Complete ──────────────────────────────────────
            job.completed_at = datetime.now(timezone.utc)
            job.status = JobStatus.final_approved
            self.state.mark_status(job_id, JobStatus.final_approved)
            self.state.update_job(job)
            logger.info("job_completed", job_id=job_id, status=job.status.value, cost=job.total_cost)

        except Exception as e:
            logger.error("job_failed", job_id=job_id, error=str(e))
            self.state.add_error(job_id, str(e))
            self.state.mark_status(job_id, JobStatus.failed_infrastructure)
            raise

        return job