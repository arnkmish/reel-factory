"""
SQLite-backed state store for production jobs.
Persists job records, stage attempts, and run events.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from reel_factory.models import (
    JobRecord, JobStatus, StageAttempt, ReviewResult,
    SelectionCandidate, ScriptPackage, StoryboardPackage,
    GeneratedImageAsset, GeneratedClipAsset, GeneratedAudioAsset,
)


class StateStore:
    """Persistent state store backed by SQLite (WAL mode)."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._migrate()
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    # ── Schema ──────────────────────────────────────────────

    def _migrate(self) -> None:
        conn = self.connect()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                run_date TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'NEW',
                language TEXT NOT NULL DEFAULT 'English',
                source_json TEXT,
                script_json TEXT,
                storyboard_json TEXT,
                final_video_path TEXT,
                drive_folder_url TEXT,
                sheets_row_updated INTEGER NOT NULL DEFAULT 0,
                used_best_so_far_fallback INTEGER NOT NULL DEFAULT 0,
                fallback_stage_list TEXT NOT NULL DEFAULT '[]',
                total_cost REAL NOT NULL DEFAULT 0.0,
                max_cost_budget REAL NOT NULL DEFAULT 5.0,
                errors_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                completed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS stage_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                stage_name TEXT NOT NULL,
                attempt_number INTEGER NOT NULL,
                artifact_json TEXT,
                review_json TEXT,
                is_clear_pass INTEGER NOT NULL DEFAULT 0,
                is_best_so_far INTEGER NOT NULL DEFAULT 0,
                timestamp TEXT NOT NULL,
                cost REAL NOT NULL DEFAULT 0.0,
                FOREIGN KEY (job_id) REFERENCES jobs(job_id)
            );

            CREATE TABLE IF NOT EXISTS images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                scene_id TEXT NOT NULL,
                attempt INTEGER NOT NULL,
                endpoint TEXT,
                model_version TEXT,
                prompt TEXT,
                seed INTEGER,
                request_id TEXT,
                output_url TEXT,
                local_path TEXT,
                drive_path TEXT,
                cost REAL NOT NULL DEFAULT 0.0,
                FOREIGN KEY (job_id) REFERENCES jobs(job_id)
            );

            CREATE TABLE IF NOT EXISTS clips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                scene_id TEXT NOT NULL,
                attempt INTEGER NOT NULL,
                source_image_url TEXT,
                endpoint TEXT,
                model_version TEXT,
                motion_prompt TEXT,
                seed INTEGER,
                request_id TEXT,
                output_url TEXT,
                local_path TEXT,
                drive_path TEXT,
                cost REAL NOT NULL DEFAULT 0.0,
                duration REAL NOT NULL DEFAULT 0.0,
                FOREIGN KEY (job_id) REFERENCES jobs(job_id)
            );

            CREATE TABLE IF NOT EXISTS audio_assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                scene_id TEXT,
                track_type TEXT NOT NULL,
                endpoint TEXT,
                model_version TEXT,
                text TEXT,
                request_id TEXT,
                output_url TEXT,
                local_path TEXT,
                drive_path TEXT,
                cost REAL NOT NULL DEFAULT 0.0,
                duration REAL NOT NULL DEFAULT 0.0,
                FOREIGN KEY (job_id) REFERENCES jobs(job_id)
            );

            CREATE INDEX IF NOT EXISTS idx_jobs_run_date ON jobs(run_date);
            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
            CREATE INDEX IF NOT EXISTS idx_attempts_job ON stage_attempts(job_id);
        """)

    # ── Job CRUD ────────────────────────────────────────────

    def create_or_resume(self, job_id: str, run_date: str) -> JobRecord:
        conn = self.connect()
        row = conn.execute(
            "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()

        if row:
            return self._row_to_job(row)

        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """INSERT INTO jobs (job_id, run_date, status, language, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (job_id, run_date, JobStatus.new.value, "English", now),
        )
        conn.commit()
        return JobRecord(job_id=job_id, run_date=run_date)

    def get_job(self, job_id: str) -> JobRecord | None:
        conn = self.connect()
        row = conn.execute(
            "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        return self._row_to_job(row) if row else None

    def update_job(self, job: JobRecord) -> None:
        conn = self.connect()
        conn.execute(
            """UPDATE jobs SET
                status = ?, language = ?,
                source_json = ?, script_json = ?, storyboard_json = ?,
                final_video_path = ?, drive_folder_url = ?,
                sheets_row_updated = ?,
                used_best_so_far_fallback = ?,
                fallback_stage_list = ?,
                total_cost = ?, max_cost_budget = ?,
                errors_json = ?, completed_at = ?
               WHERE job_id = ?""",
            (
                job.status.value, job.language,
                self._to_json(job.source), self._to_json(job.script),
                self._to_json(job.storyboard),
                job.final_video_path, job.drive_folder_url,
                int(job.sheets_row_updated),
                int(job.used_best_so_far_fallback),
                json.dumps(job.fallback_stage_list),
                job.total_cost, job.max_cost_budget,
                json.dumps(job.errors),
                job.completed_at.isoformat() if job.completed_at else None,
                job.job_id,
            ),
        )
        conn.commit()

    def mark_status(self, job_id: str, status: JobStatus) -> None:
        conn = self.connect()
        conn.execute(
            "UPDATE jobs SET status = ? WHERE job_id = ?",
            (status.value, job_id),
        )
        conn.commit()

    def add_error(self, job_id: str, error: str) -> None:
        conn = self.connect()
        row = conn.execute(
            "SELECT errors_json FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        errors = json.loads(row["errors_json"]) if row else []
        errors.append(error)
        conn.execute(
            "UPDATE jobs SET errors_json = ? WHERE job_id = ?",
            (json.dumps(errors), job_id),
        )
        conn.commit()

    # ── Attempts ────────────────────────────────────────────

    def record_attempt(self, job_id: str, attempt: StageAttempt) -> None:
        conn = self.connect()
        conn.execute(
            """INSERT INTO stage_attempts
               (job_id, stage_name, attempt_number, artifact_json,
                review_json, is_clear_pass, is_best_so_far,
                timestamp, cost)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job_id, attempt.stage_name, attempt.attempt_number,
                self._to_json(attempt.artifact),
                self._to_json(attempt.review),
                int(attempt.is_clear_pass),
                int(attempt.is_best_so_far),
                attempt.timestamp.isoformat(),
                attempt.cost,
            ),
        )
        conn.commit()

    def get_attempts(self, job_id: str, stage_name: str) -> List[StageAttempt]:
        conn = self.connect()
        rows = conn.execute(
            """SELECT * FROM stage_attempts
               WHERE job_id = ? AND stage_name = ?
               ORDER BY attempt_number ASC""",
            (job_id, stage_name),
        ).fetchall()
        return [self._row_to_attempt(r) for r in rows]

    # ── Asset recording ────────────────────────────────────

    def record_image(self, job_id: str, image: GeneratedImageAsset) -> None:
        conn = self.connect()
        conn.execute(
            """INSERT INTO images
               (job_id, scene_id, attempt, endpoint, model_version,
                prompt, seed, request_id, output_url, local_path,
                drive_path, cost)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job_id, image.scene_id, image.attempt,
                image.endpoint, image.model_version,
                image.prompt, image.seed, image.request_id,
                image.output_url, image.local_path,
                image.drive_path, image.cost,
            ),
        )
        conn.commit()

    def record_clip(self, job_id: str, clip: GeneratedClipAsset) -> None:
        conn = self.connect()
        conn.execute(
            """INSERT INTO clips
               (job_id, scene_id, attempt, source_image_url,
                endpoint, model_version, motion_prompt, seed,
                request_id, output_url, local_path, drive_path,
                cost, duration)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job_id, clip.scene_id, clip.attempt,
                clip.source_image_url, clip.endpoint,
                clip.model_version, clip.motion_prompt, clip.seed,
                clip.request_id, clip.output_url, clip.local_path,
                clip.drive_path, clip.cost, clip.duration,
            ),
        )
        conn.commit()

    def record_audio(self, job_id: str, audio: GeneratedAudioAsset) -> None:
        conn = self.connect()
        conn.execute(
            """INSERT INTO audio_assets
               (job_id, scene_id, track_type, endpoint, model_version,
                text, request_id, output_url, local_path,
                drive_path, cost, duration)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job_id, audio.scene_id, audio.track_type, audio.endpoint,
                audio.model_version, audio.text, audio.request_id,
                audio.output_url, audio.local_path, audio.drive_path,
                audio.cost, audio.duration,
            ),
        )
        conn.commit()

    # ── Helpers ─────────────────────────────────────────────

    @staticmethod
    def _to_json(obj: Any) -> str | None:
        if obj is None:
            return None
        if hasattr(obj, "model_dump"):
            return json.dumps(obj.model_dump(mode="json"))
        return json.dumps(obj)

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> JobRecord:
        return JobRecord(
            job_id=row["job_id"],
            run_date=row["run_date"],
            status=JobStatus(row["status"]),
            language=row["language"],
            source=StateStore._from_json(row["source_json"], SelectionCandidate),
            script=StateStore._from_json(row["script_json"], ScriptPackage),
            storyboard=StateStore._from_json(row["storyboard_json"], StoryboardPackage),
            final_video_path=row["final_video_path"],
            drive_folder_url=row["drive_folder_url"],
            sheets_row_updated=bool(row["sheets_row_updated"]),
            used_best_so_far_fallback=bool(row["used_best_so_far_fallback"]),
            fallback_stage_list=json.loads(row["fallback_stage_list"]),
            total_cost=row["total_cost"],
            max_cost_budget=row["max_cost_budget"],
            errors=json.loads(row["errors_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
        )

    @staticmethod
    def _from_json(json_str: str | None, model_class: type) -> Any | None:
        if not json_str:
            return None
        data = json.loads(json_str)
        return model_class(**data)

    @staticmethod
    def _row_to_attempt(row: sqlite3.Row) -> StageAttempt:
        return StageAttempt(
            stage_name=row["stage_name"],
            attempt_number=row["attempt_number"],
            artifact=StateStore._from_json(row["artifact_json"], dict),
            review=StateStore._from_json(row["review_json"], ReviewResult),
            is_clear_pass=bool(row["is_clear_pass"]),
            is_best_so_far=bool(row["is_best_so_far"]),
            timestamp=datetime.fromisoformat(row["timestamp"]),
            cost=row["cost"],
        )
