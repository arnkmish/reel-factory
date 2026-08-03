import pytest

from reel_factory.models import ReviewResult, StageAttempt
from reel_factory.review_loop import ReviewLoop


def test_review_loop_clear_pass_first_attempt():
    """Should return immediately when first attempt clears threshold."""
    loop = ReviewLoop("script")

    def generate(feedback):
        return {"text": "good script"}, 0.05

    def review(artifact):
        return ReviewResult(
            passed=True,
            overall_score=9.0,
            reviewer_model="test",
            review_prompt_version="v1",
        )

    artifact, is_clear, attempts = loop.run(generate, review)
    assert is_clear is True
    assert len(attempts) == 1
    assert loop.used_best_so_far_fallback is False


def test_review_loop_clear_pass_third_attempt():
    """Should pass on the third attempt after two failures."""
    loop = ReviewLoop("images")
    call_count = [0]

    def generate(feedback):
        call_count[0] += 1
        return {"scene": f"attempt_{call_count[0]}"}, 0.10

    def review(artifact):
        score = {1: 5.0, 2: 7.5, 3: 9.0}.get(call_count[0], 5.0)
        return ReviewResult(
            passed=score > 8.0,
            overall_score=score,
            reviewer_model="test",
            review_prompt_version="v1",
            fix_instructions=["Improve composition."],
        )

    artifact, is_clear, attempts = loop.run(generate, review)
    assert is_clear is True
    assert len(attempts) == 3
    assert loop.best_score == 9.0


def test_review_loop_best_so_far_fallback():
    """Should return best-so-far when no attempt clears threshold."""
    loop = ReviewLoop("shots")

    def generate(feedback):
        return {"clip": "test"}, 0.15

    def review(artifact):
        return ReviewResult(
            passed=False,
            overall_score=6.5,
            reviewer_model="test",
            review_prompt_version="v1",
            fix_instructions=["Reduce motion."],
        )

    artifact, is_clear, attempts = loop.run(generate, review)
    assert is_clear is False
    assert len(attempts) == 3
    assert loop.used_best_so_far_fallback is True
    assert loop.best_score == 6.5


def test_review_loop_tracks_best_so_far():
    """Should correctly track the best-scoring attempt."""
    loop = ReviewLoop("final")
    scores = [4.0, 7.0, 6.0]
    call_count = [0]

    def generate(feedback):
        call_count[0] += 1
        return {"video": f"version_{call_count[0]}"}, 0.20

    def review(artifact):
        score = scores[call_count[0] - 1]
        return ReviewResult(
            passed=False,
            overall_score=score,
            reviewer_model="test",
            review_prompt_version="v1",
        )

    artifact, is_clear, attempts = loop.run(generate, review)
    assert is_clear is False
    assert loop.best_score == 7.0
    # The best artifact should be from attempt 2 (score 7.0)
    assert artifact["video"] == "version_2"


def test_review_loop_attempts_have_correct_metadata():
    """Each attempt should have proper stage metadata."""
    loop = ReviewLoop("source")

    def generate(feedback):
        return {"source": "test"}, 0.01

    def review(artifact):
        return ReviewResult(
            passed=True,
            overall_score=9.5,
            reviewer_model="test",
            review_prompt_version="v1",
        )

    _, _, attempts = loop.run(generate, review)
    assert len(attempts) == 1
    assert attempts[0].stage_name == "source"
    assert attempts[0].attempt_number == 1
    assert attempts[0].is_clear_pass is True
    assert attempts[0].cost == 0.01
