"""
Generic review loop implementing the v1 scoring and retry policy.
"""
from __future__ import annotations

from typing import Any, Callable, List, Optional, Tuple

from reel_factory.models import ReviewResult, StageAttempt


class ReviewLoop:
    """
    Orchestrates a single reviewable stage with:
    - Max 3 attempts
    - Pass threshold > 8.0 / 10
    - Best-so-far fallback
    """

    PASS_THRESHOLD = 8.0
    MAX_ATTEMPTS = 3

    def __init__(self, stage_name: str):
        self.stage_name = stage_name
        self.attempts: List[StageAttempt] = []

    def run(
        self,
        generate_fn: Callable[[Optional[str]], Tuple[Any, float]],
        review_fn: Callable[[Any], ReviewResult],
    ) -> Tuple[Any, bool, List[StageAttempt]]:
        """
        Execute the review loop.
        
        Returns:
            (best_artifact, is_clear_pass, all_attempts)
        """
        best_artifact = None
        best_review: Optional[ReviewResult] = None
        previous_feedback: Optional[str] = None

        for attempt_num in range(1, self.MAX_ATTEMPTS + 1):
            # Generate
            artifact, cost = generate_fn(previous_feedback)

            # Review
            review = review_fn(artifact)

            # Track best-so-far
            if best_review is None or review.overall_score > best_review.overall_score:
                best_artifact = artifact
                best_review = review

            # Record attempt
            attempt = StageAttempt(
                stage_name=self.stage_name,
                attempt_number=attempt_num,
                artifact=artifact,
                review=review,
                is_clear_pass=review.is_clear_pass,
                is_best_so_far=(best_review is not None and review.overall_score >= best_review.overall_score),
                cost=cost,
            )
            self.attempts.append(attempt)

            # Check for clear pass
            if review.is_clear_pass:
                return artifact, True, self.attempts

            # Prepare feedback for next attempt
            if review.fix_instructions:
                previous_feedback = "; ".join(review.fix_instructions)
            else:
                previous_feedback = f"Score {review.overall_score}/10, needs improvement."

        # No clear pass after max attempts — return best-so-far
        return best_artifact, False, self.attempts

    @property
    def used_best_so_far_fallback(self) -> bool:
        return len(self.attempts) >= self.MAX_ATTEMPTS and not self.attempts[-1].is_clear_pass

    @property
    def best_score(self) -> float:
        scores = [a.review.overall_score for a in self.attempts if a.review]
        return max(scores) if scores else 0.0
