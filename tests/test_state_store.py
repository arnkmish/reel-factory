import json
import tempfile
from pathlib import Path

import pytest

from reel_factory.models import (
    JobRecord, JobStatus, StageAttempt, ReviewResult,
    SelectionCandidate, CorpusItem, ScriptScene, ScriptPackage,
    GeneratedImageAsset, GeneratedAudioAsset,
)
from reel_factory.state_store import StateStore


@pytest.fixture
def store():
    """Create a temporary SQLite database for each test."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    s = StateStore(db_path)
    s.connect()
    yield s
    s.close()
    Path(db_path).unlink(missing_ok=True)


def test_create_new_job(store):
    job = store.create_or_resume("test-001", "2026-07-23")
    assert job.job_id == "test-001"
    assert job.run_date == "2026-07-23"
    assert job.status == JobStatus.new
    assert job.language == "English"
    assert job.max_cost_budget == 5.0


def test_resume_existing_job(store):
    job1 = store.create_or_resume("test-002", "2026-07-23")
    job2 = store.create_or_resume("test-002", "2026-07-23")
    assert job1.job_id == job2.job_id
    assert job2.status == JobStatus.new


def test_get_job(store):
    store.create_or_resume("test-003", "2026-07-23")
    job = store.get_job("test-003")
    assert job is not None
    assert job.job_id == "test-003"


def test_get_missing_job(store):
    job = store.get_job("nonexistent")
    assert job is None


def test_update_job(store):
    job = store.create_or_resume("test-004", "2026-07-23")
    job.status = JobStatus.archived_to_drive
    job.total_cost = 3.50
    job.used_best_so_far_fallback = True
    job.fallback_stage_list = ["images"]
    store.update_job(job)

    reloaded = store.get_job("test-004")
    assert reloaded.status == JobStatus.archived_to_drive
    assert reloaded.total_cost == 3.50
    assert reloaded.used_best_so_far_fallback is True
    assert reloaded.fallback_stage_list == ["images"]


def test_mark_status(store):
    store.create_or_resume("test-005", "2026-07-23")
    store.mark_status("test-005", JobStatus.archived_to_drive)
    job = store.get_job("test-005")
    assert job.status == JobStatus.archived_to_drive


def test_add_error(store):
    store.create_or_resume("test-006", "2026-07-23")
    store.add_error("test-006", "fal API timeout")
    job = store.get_job("test-006")
    assert "fal API timeout" in job.errors


def test_record_and_get_attempts(store):
    store.create_or_resume("test-007", "2026-07-23")
    review = ReviewResult(passed=True, overall_score=9.0, reviewer_model="test")
    attempt = StageAttempt(
        stage_name="script",
        attempt_number=1,
        review=review,
        is_clear_pass=True,
        is_best_so_far=True,
        cost=0.05,
    )
    store.record_attempt("test-007", attempt)

    attempts = store.get_attempts("test-007", "script")
    assert len(attempts) == 1
    assert attempts[0].is_clear_pass is True
    assert attempts[0].review.overall_score == 9.0


def test_record_image(store):
    store.create_or_resume("test-008", "2026-07-23")
    img = GeneratedImageAsset(
        scene_id="S01", attempt=1, endpoint="fal-ai/test",
        model_version="v1", prompt="test", seed=42,
        request_id="req-1", output_url="https://example.com/img.png",
        cost=0.10,
    )
    store.record_image("test-008", img)
    # Verify by checking the job record still exists
    job = store.get_job("test-008")
    assert job is not None


def test_record_audio(store):
    store.create_or_resume("test-010", "2026-07-23")
    audio = GeneratedAudioAsset(
        track_type="narration", endpoint="fal-ai/tts",
        model_version="v1", text="Hello world",
        request_id="req-1", output_url="https://example.com/audio.mp3",
        cost=0.05, duration=3.0,
    )
    store.record_audio("test-010", audio)
    job = store.get_job("test-010")
    assert job is not None


def test_job_with_source(store):
    job = store.create_or_resume("test-011", "2026-07-23")
    item = CorpusItem(
        source_id="gita-2-47", tradition="Hindu",
        work="Bhagavad Gita", approved_translation="Do your duty",
        license="public-domain",
    )
    candidate = SelectionCandidate(
        corpus_item=item, treatment_summary="A teaching on duty",
        source_confidence=0.95, clarity_score=0.9,
        emotional_resonance=0.8, visual_potential=0.7,
        novelty_score=0.6, cultural_risk=0.1,
        suitability_score=0.85, overall_score=0.82,
    )
    job.source = candidate
    store.update_job(job)

    reloaded = store.get_job("test-011")
    assert reloaded.source is not None
    assert reloaded.source.corpus_item.source_id == "gita-2-47"
    assert reloaded.source.overall_score == 0.82