import pytest
from reel_factory.models import (
    CorpusItem, SelectionCandidate, ScriptScene, ScriptPackage,
    StoryboardScene, StoryboardPackage, GeneratedImageAsset,
    GeneratedAudioAsset, ReviewIssue, ReviewResult,
    StageAttempt, JobRecord, DriveManifest, SheetsRow,
    QuoteMode, RiskTier, Severity, JobStatus
)


def test_corpus_item_defaults():
    item = CorpusItem(
        source_id="gita-2-47",
        tradition="Hindu",
        work="Bhagavad Gita",
        approved_translation="Do your duty...",
        license="public-domain"
    )
    assert item.risk_tier == RiskTier.low
    assert item.content_type == "teaching"
    assert item.depiction_policy == "symbolic-preferred"


def test_selection_candidate_scoring():
    item = CorpusItem(
        source_id="test-1", tradition="Test", work="Test",
        approved_translation="Test", license="public-domain"
    )
    candidate = SelectionCandidate(
        corpus_item=item,
        treatment_summary="A short moral story",
        source_confidence=0.95,
        clarity_score=0.9,
        emotional_resonance=0.8,
        visual_potential=0.7,
        novelty_score=0.6,
        cultural_risk=0.1,
        suitability_score=0.85,
        overall_score=0.82,
        quote_mode=QuoteMode.paraphrase
    )
    assert candidate.overall_score == 0.82
    assert candidate.quote_mode == QuoteMode.paraphrase


def test_script_package_validation():
    scenes = [
        ScriptScene(scene_id="S01", duration=4, screen_text="Hello", story_function="hook"),
        ScriptScene(scene_id="S02", duration=5, screen_text="World", story_function="narrative"),
        ScriptScene(scene_id="S03", duration=4, screen_text="Test", story_function="narrative"),
        ScriptScene(scene_id="S04", duration=4, screen_text="More", story_function="narrative"),
        ScriptScene(scene_id="S05", duration=5, screen_text="End", story_function="moral"),
    ]
    script = ScriptPackage(
        title="Test Story",
        hook="Once upon a time...",
        duration_seconds=30,
        scenes=scenes,
        final_moral="Be kind.",
        source_credit="Source: Test",
        caption="A short story",
        hashtags=["#wisdom"]
    )
    assert len(script.scenes) == 5
    assert script.duration_seconds == 30


def test_review_result_clear_pass():
    review = ReviewResult(
        passed=True,
        overall_score=9.0,
        reviewer_model="test-model",
        review_prompt_version="v1"
    )
    assert review.is_clear_pass is True


def test_review_result_not_clear_pass():
    review = ReviewResult(
        passed=True,
        overall_score=7.5,
        reviewer_model="test-model",
        review_prompt_version="v1"
    )
    assert review.is_clear_pass is False


def test_review_result_blocking_issue():
    issue = ReviewIssue(
        code="SOURCE_CONTEXT_LOST",
        severity=Severity.blocking,
        location="scene_4",
        evidence="The script changes the meaning.",
        fix="Rewrite the outcome."
    )
    review = ReviewResult(
        passed=False,
        overall_score=5.0,
        blocking_issues=[issue],
        reviewer_model="test-model",
        review_prompt_version="v1"
    )
    assert len(review.blocking_issues) == 1
    assert review.blocking_issues[0].severity == Severity.blocking


def test_job_record_defaults():
    job = JobRecord(job_id="test-001", run_date="2026-07-23")
    assert job.status == JobStatus.new
    assert job.language == "English"
    assert job.max_cost_budget == 5.0
    assert job.used_best_so_far_fallback is False
    assert job.total_cost == 0.0
    assert job.images == []  # v2: no clips field anymore
    assert job.audio == []


def test_job_record_cost_budget():
    job = JobRecord(job_id="test-002", run_date="2026-07-23", total_cost=4.50)
    assert job.total_cost <= job.max_cost_budget


def test_drive_manifest():
    manifest = DriveManifest(
        job_id="test-001",
        run_date="2026-07-23",
        status="ARCHIVED_TO_DRIVE",
        scene_count=5,
        image_count=5,
        total_cost=3.50
    )
    assert manifest.status == "ARCHIVED_TO_DRIVE"
    assert manifest.total_cost == 3.50


def test_sheets_row():
    row = SheetsRow(
        job_id="test-001",
        run_date="2026-07-23",
        status="ARCHIVED_TO_DRIVE",
        script_score=8.5,
        final_score=9.0,
        actual_cost=3.50
    )
    assert row.publishing_status == "DISABLED_V1"
    assert row.actual_cost == 3.50


def test_stage_attempt():
    attempt = StageAttempt(
        stage_name="script",
        attempt_number=1,
        is_clear_pass=True,
        is_best_so_far=True,
        cost=0.05
    )
    assert attempt.stage_name == "script"
    assert attempt.is_clear_pass is True