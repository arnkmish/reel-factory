"""
Pydantic domain models for the Reel Factory workflow.
These define the strict contracts for every stage of the pipeline.
v2: Video clip assets removed — uses static frames + FFmpeg assembly.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────

class QuoteMode(str, Enum):
    direct_quote = "direct_quote"
    paraphrase = "paraphrase"
    inspired = "inspired"


class RiskTier(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class JobStatus(str, Enum):
    new = "NEW"
    source_selected = "SOURCE_SELECTED"
    source_approved = "SOURCE_APPROVED"
    script_approved = "SCRIPT_APPROVED"
    storyboard_approved = "STORYBOARD_APPROVED"
    images_approved = "IMAGES_APPROVED"
    assembled = "ASSEMBLED"
    final_approved = "FINAL_APPROVED"
    archived_to_drive = "ARCHIVED_TO_DRIVE"
    uploaded_private = "UPLOADED_PRIVATE"
    published = "PUBLISHED"
    retryable = "RETRYABLE"
    quarantined = "QUARANTINED"
    failed_infrastructure = "FAILED_INFRASTRUCTURE"
    skipped_overlap = "SKIPPED_OVERLAP"
    skipped_no_source = "SKIPPED_NO_ELIGIBLE_SOURCE"


class Severity(str, Enum):
    blocking = "blocking"
    non_blocking = "non_blocking"


# ──────────────────────────────────────────────
# Corpus & Selection
# ──────────────────────────────────────────────

class CorpusItem(BaseModel):
    """A single approved entry in the content corpus."""
    source_id: str = Field(..., description="Unique stable identifier")
    tradition: str
    work: str
    location: Dict[str, Any] = Field(default_factory=dict)
    source_language: str = "English"
    approved_translation: str
    translation_author: Optional[str] = None
    license: str
    source_url: Optional[str] = None
    content_type: str = "teaching"
    allowed_use: List[str] = Field(default_factory=lambda: ["paraphrase", "short_quote"])
    context_summary: Optional[str] = None
    interpretation_boundaries: List[str] = Field(default_factory=list)
    sensitivity_flags: List[str] = Field(default_factory=list)
    depiction_policy: str = "symbolic-preferred"
    verified_by: List[str] = Field(default_factory=list)
    corpus_version: str = "2026-07-01"
    risk_tier: RiskTier = RiskTier.low


class SelectionCandidate(BaseModel):
    """A candidate item selected for today's production, with scoring."""
    corpus_item: CorpusItem
    treatment_summary: str
    source_confidence: float = Field(ge=0.0, le=1.0)
    clarity_score: float = Field(ge=0.0, le=1.0)
    emotional_resonance: float = Field(ge=0.0, le=1.0)
    visual_potential: float = Field(ge=0.0, le=1.0)
    novelty_score: float = Field(ge=0.0, le=1.0)
    cultural_risk: float = Field(ge=0.0, le=1.0)
    suitability_score: float = Field(ge=0.0, le=1.0)
    overall_score: float = Field(ge=0.0, le=1.0)
    quote_mode: QuoteMode = QuoteMode.paraphrase


# ──────────────────────────────────────────────
# Script & Storyboard
# ──────────────────────────────────────────────

class ScriptScene(BaseModel):
    """A single scene within the script."""
    scene_id: str
    duration: int = Field(ge=2, le=10)
    screen_text: str
    narration: Optional[str] = None
    story_function: str = "narrative"


class ScriptPackage(BaseModel):
    """The complete script for a reel."""
    title: str
    hook: str
    duration_seconds: int = Field(ge=20, le=45)
    quote_mode: QuoteMode = QuoteMode.paraphrase
    scenes: List[ScriptScene] = Field(..., min_length=5, max_length=8)
    final_moral: str
    source_credit: str
    caption: str
    hashtags: List[str] = Field(default_factory=list)


class StoryboardScene(BaseModel):
    """A single storyboard scene with visual direction."""
    scene_id: str
    visual_description: str
    characters: List[str] = Field(default_factory=list)
    setting: str
    composition: str
    camera: str = "medium-wide"
    palette: List[str] = Field(default_factory=list)
    symbols: List[str] = Field(default_factory=list)
    image_prompt: str
    negative_prompt: Optional[str] = None
    motion_prompt: Optional[str] = None  # kept for API compat, unused in v2
    text_safe_zone: str = "upper_center"
    depiction_notes: List[str] = Field(default_factory=list)


class StoryboardPackage(BaseModel):
    """The complete storyboard for a reel."""
    scenes: List[StoryboardScene] = Field(..., min_length=5, max_length=8)
    character_sheet: Optional[str] = None
    setting_bible: Optional[str] = None
    palette: List[str] = Field(default_factory=list)
    illustration_style: str = "minimal_symbolic_spiritual"
    aspect_ratio: str = "9:16"


# ──────────────────────────────────────────────
# Generated Assets
# ──────────────────────────────────────────────

class GeneratedImageAsset(BaseModel):
    """Metadata for a single generated image."""
    scene_id: str
    attempt: int = Field(ge=1, le=3)
    endpoint: str
    model_version: str
    prompt: str
    negative_prompt: Optional[str] = None
    seed: int
    request_id: str
    output_url: str
    local_path: Optional[str] = None
    drive_path: Optional[str] = None
    cost: float = 0.0
    width: int = 1080
    height: int = 1920


class GeneratedAudioAsset(BaseModel):
    """Metadata for a generated audio track (narration or music)."""
    track_type: str = Field(..., pattern="^(narration|music)$")
    scene_id: Optional[str] = None  # set for per-scene narration
    endpoint: str
    model_version: str
    text: Optional[str] = None
    request_id: str = ""
    output_url: str = ""
    local_path: Optional[str] = None
    drive_path: Optional[str] = None
    cost: float = 0.0
    duration: float = 0.0


# ──────────────────────────────────────────────
# Review
# ──────────────────────────────────────────────

class ReviewIssue(BaseModel):
    """A single issue found during review."""
    code: str
    severity: Severity = Severity.non_blocking
    location: Optional[str] = None
    evidence: str
    fix: Optional[str] = None


class ReviewResult(BaseModel):
    """Structured output from a reviewer agent."""
    passed: bool = Field(default=False, description="Whether the review passed")
    overall_score: float = Field(ge=0.0, le=10.0)
    score_scale: int = 10
    clear_pass_threshold: float = 8.0
    blocking_issues: List[ReviewIssue] = Field(default_factory=list)
    non_blocking_issues: List[ReviewIssue] = Field(default_factory=list)
    dimension_scores: Dict[str, float] = Field(default_factory=dict)
    fix_instructions: List[str] = Field(default_factory=list)
    reviewer_model: str = "unknown"
    review_prompt_version: str = "v1"

    @field_validator("overall_score")
    @classmethod
    def score_must_be_on_scale(cls, v: float) -> float:
        if v < 0.0 or v > 10.0:
            raise ValueError("overall_score must be between 0.0 and 10.0")
        return v

    @property
    def is_clear_pass(self) -> bool:
        return self.passed and self.overall_score > self.clear_pass_threshold


class StageAttempt(BaseModel):
    """Record of a single attempt at a stage."""
    stage_name: str
    attempt_number: int = Field(ge=1, le=3)
    artifact: Optional[Any] = None
    review: Optional[ReviewResult] = None
    is_clear_pass: bool = False
    is_best_so_far: bool = False
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    cost: float = 0.0


# ──────────────────────────────────────────────
# Job & Manifest
# ──────────────────────────────────────────────

class JobRecord(BaseModel):
    """The full record of a production job."""
    job_id: str
    run_date: str
    status: JobStatus = JobStatus.new
    language: str = "English"
    source: Optional[SelectionCandidate] = None
    script: Optional[ScriptPackage] = None
    storyboard: Optional[StoryboardPackage] = None
    images: List[GeneratedImageAsset] = Field(default_factory=list)
    audio: List[GeneratedAudioAsset] = Field(default_factory=list)
    final_video_path: Optional[str] = None
    drive_folder_url: Optional[str] = None
    sheets_row_updated: bool = False
    attempts: Dict[str, List[StageAttempt]] = Field(default_factory=dict)
    used_best_so_far_fallback: bool = False
    fallback_stage_list: List[str] = Field(default_factory=list)
    total_cost: float = 0.0
    max_cost_budget: float = 5.0
    errors: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None


class DriveManifest(BaseModel):
    """Manifest file stored alongside assets in Google Drive."""
    job_id: str
    run_date: str
    status: str
    source_id: Optional[str] = None
    script_title: Optional[str] = None
    scene_count: int = 0
    image_count: int = 0
    audio_count: int = 0
    review_scores: Dict[str, float] = Field(default_factory=dict)
    attempt_counts: Dict[str, int] = Field(default_factory=dict)
    used_best_so_far: bool = False
    total_cost: float = 0.0
    models_used: Dict[str, str] = Field(default_factory=dict)
    created_at: str = ""


class SheetsRow(BaseModel):
    """A single row in the Google Sheets production log."""
    job_id: str
    run_date: str
    status: str
    language: str = "English"
    source_family: Optional[str] = None
    source_id: Optional[str] = None
    quote_mode: Optional[str] = None
    script_score: Optional[float] = None
    storyboard_score: Optional[float] = None
    image_score: Optional[float] = None
    shot_score: Optional[float] = None
    final_score: Optional[float] = None
    source_attempts: int = 0
    script_attempts: int = 0
    image_attempts: int = 0
    shot_attempts: int = 0
    final_attempts: int = 0
    used_best_so_far_fallback: bool = False
    fallback_stage_list: str = ""
    drive_folder_url: Optional[str] = None
    final_video_path: Optional[str] = None
    publishing_status: str = "DISABLED_V1"
    actual_cost: float = 0.0
    last_error: Optional[str] = None