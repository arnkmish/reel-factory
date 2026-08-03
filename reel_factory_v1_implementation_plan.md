# Reel Factory V1 Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build a working v1 of the reel-generation system in `/opt/data/VideoGeneratorBusinessRepo/` that selects from an approved corpus, generates a short vertical video, scores each stage, stores artifacts in Google Drive, and logs tracking data to Google Sheets.

**Strict v1 Constraint:** The daily cron scheduler must **not** be enabled until a manual Proof-of-Concept (PoC) run is completed and approved by the user.

**Architecture:** Python is the workflow engine and source of truth. Hermes is used only for bounded generation/review tasks with structured JSON outputs. FFmpeg/Pillow/OCR/state persistence remain deterministic Python code.

**Tech Stack:** Python 3.13 via `uv`, Pydantic, SQLite, structlog, Tenacity, Pillow, FFmpeg/ffprobe, fal-client, google-api-python-client, gspread, pytesseract or equivalent OCR, pytest.

---

## Locked V1 Product Decisions

These are implementation requirements, not suggestions:

- Generate and review only; publishing is disabled.
- English only.
- Mix of fables and scripture-based teachings.
- All approved source families may be selected.
- Direct quotes and paraphrases are both allowed by default.
- Visual style defaults to minimal symbolic / spiritual.
- Audio must come from a dedicated audio/TTS path; never use video-model native audio.
- Default audio behavior: TTS narration plus optional background music.
- Google Drive is the asset/archive store.
- Google Sheets is the reporting/tracking surface.
- Pass threshold is `> 8.0 / 10`.
- Three total attempts per reviewable stage.
- If no attempt clears the threshold, continue with the best-so-far candidate and mark the stage as downgraded.
- - No human review in the v1 critical path.
 - Budget constraint: a single video should not cost more than **$5 USD** in fal API fees.

---

## Current Context / Assumptions

- Current folder contents are documentation-only; there is no implementation yet.
- Treat `/opt/data/VideoGeneratorBusinessRepo/` as the project root.
- V1 must create a runnable local CLI before any cron wiring.
- V1 must stop after Drive archival and Sheets logging.
- Publishing modules can exist as interfaces/stubs, but must be disabled by config and uncalled by the v1 run path.

---

## Proposed Repository Layout

Use the existing blueprint layout, but narrow it for v1:

```text
/opt/data/VideoGeneratorBusinessRepo/
├── README.md
├── pyproject.toml
├── .env.example
├── config/
│   ├── app.yaml
│   ├── models.yaml
│   ├── review_thresholds.yaml
│   ├── visual_styles.yaml
│   └── drive_sheets.yaml
├── corpus/
│   ├── manifests/
│   └── normalized/
├── prompts/
│   ├── idea_selector.md
│   ├── source_verifier.md
│   ├── story_adapter.md
│   ├── storyboard_director.md
│   ├── image_reviewer.md
│   ├── shot_reviewer.md
│   └── final_video_reviewer.md
├── src/reel_factory/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   ├── models.py
│   ├── state_store.py
│   ├── logging.py
│   ├── corpus.py
│   ├── selection.py
│   ├── hermes_client.py
│   ├── review_loop.py
│   ├── image_pipeline.py
│   ├── video_pipeline.py
│   ├── audio_pipeline.py
│   ├── assembly.py
│   ├── ocr.py
│   ├── drive.py
│   ├── sheets.py
│   └── workflow.py
├── tests/
│   ├── test_config.py
│   ├── test_state_store.py
│   ├── test_selection.py
│   ├── test_review_loop.py
│   ├── test_assembly.py
│   ├── test_ocr.py
│   └── test_workflow_smoke.py
├── runtime/
│   ├── jobs/
│   ├── logs/
│   └── cache/
└── docs/
    └── runbooks/
```

---

## Stage Contracts To Implement First

Create these Pydantic models before building adapters:

1. `CorpusItem`
2. `SelectionCandidate`
3. `ScriptScene`
4. `ScriptPackage`
5. `StoryboardScene`
6. `StoryboardPackage`
7. `GeneratedImageAsset`
8. `GeneratedClipAsset`
9. `GeneratedAudioAsset`
10. `ReviewIssue`
11. `ReviewResult`
12. `StageAttempt`
13. `JobRecord`
14. `DriveManifest`
15. `SheetsRow`

Required `ReviewResult` fields:

- `pass: bool`
- `overall_score: float`
- `score_scale: int = 10`
- `clear_pass_threshold: float = 8.0`
- `blocking_issues: list[ReviewIssue]`
- `non_blocking_issues: list[ReviewIssue]`
- `fix_instructions: list[str]`
- `reviewer_model: str`
- `review_prompt_version: str`

---

## Execution Milestones

### Milestone 1 — Scaffold and local run path
Success means: `uv run python -m reel_factory.cli doctor` and `uv run python -m reel_factory.cli run-daily --date 2026-07-23 --dry-run` both work.

### Milestone 2 — Corpus + review loop
Success means: the system can select an approved corpus item, produce structured script/storyboard artifacts, and score them with retry/best-so-far logic.

### Milestone 3 — Media generation and deterministic assembly
Success means: image generation, motion generation, OCR/text overlay, TTS, and final MP4 assembly work end-to-end locally.

### Milestone 4 — Drive/Sheets integration
Success means: a completed run writes all artifacts to Drive and a complete row to Sheets.

### Milestone 5 — Cron-ready v1
Success means: the local CLI can be triggered non-interactively and is safe to schedule daily, while still not publishing.

---

## Task-by-Task Plan

### Task 1: Create the Python project skeleton

**Objective:** Establish a runnable Python package and dependency-managed repo.

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `src/reel_factory/__init__.py`
- Create: `src/reel_factory/cli.py`
- Create: `tests/test_config.py`

**Steps:**
1. Create `pyproject.toml` with project metadata and dependencies.
2. Add a console entry point for `reel-factory`.
3. Create a minimal CLI with `doctor` and `run-daily` commands.
4. Add a smoke test that imports the package.

**Validation:**
- `uv run python -m reel_factory.cli doctor`
- `uv run pytest tests/test_config.py -v`

---

### Task 2: Add configuration loading and `.env.example`

**Objective:** Centralize app/model/storage/review settings.

**Files:**
- Create: `.env.example`
- Create: `config/app.yaml`
- Create: `config/models.yaml`
- Create: `config/review_thresholds.yaml`
- Create: `config/visual_styles.yaml`
- Create: `config/drive_sheets.yaml`
- Create: `src/reel_factory/config.py`
- Test: `tests/test_config.py`

**Steps:**
1. Define YAML config structure matching the locked v1 decisions.
2. Add env placeholders for fal, Google, Hermes integration, and runtime paths.
3. Load config with validation and defaults.
4. Fail fast on missing required config.

**Validation:**
- `uv run pytest tests/test_config.py -v`
- `uv run python -m reel_factory.cli doctor`

---

### Task 3: Define Pydantic domain models

**Objective:** Freeze stage I/O contracts before writing adapters.

**Files:**
- Create: `src/reel_factory/models.py`
- Test: `tests/test_config.py`

**Steps:**
1. Implement the 15 core models listed above.
2. Encode `pass_threshold=8.0`, `score_scale=10`, and attempt counts in validated config/model fields.
3. Add round-trip serialization tests.

**Validation:**
- `uv run pytest tests/test_config.py -v -k model`

---

### Task 4: Build the SQLite state store

**Objective:** Persist jobs, attempts, statuses, artifacts, and downgrade reasons.

**Files:**
- Create: `src/reel_factory/state_store.py`
- Create: `runtime/jobs/.gitkeep`
- Test: `tests/test_state_store.py`

**Steps:**
1. Define SQLite tables for jobs, stage_attempts, artifacts, and run_events.
2. Add helpers for `create_or_resume`, `record_attempt`, `mark_stage_result`, `complete`, and `fail`.
3. Store best-so-far metadata separately from clear passes.

**Validation:**
- `uv run pytest tests/test_state_store.py -v`

---

### Task 5: Build corpus ingestion and selection primitives

**Objective:** Make the workflow select only approved corpus items.

**Files:**
- Create: `src/reel_factory/corpus.py`
- Create: `src/reel_factory/selection.py`
- Create: `corpus/manifests/README.md`
- Test: `tests/test_selection.py`

**Steps:**
1. Define on-disk JSON/YAML record format for `CorpusItem`.
2. Load only items with approval/licensing fields present.
3. Add selection filters for used-history, sensitivity flags, and language compatibility.
4. Implement a scoring-based candidate ranking function.

**Validation:**
- `uv run pytest tests/test_selection.py -v`

---

### Task 6: Add Hermes adapter for bounded structured tasks

**Objective:** Wrap all Hermes generation/review interactions behind one Python interface.

**Files:**
- Create: `src/reel_factory/hermes_client.py`
- Create: `prompts/idea_selector.md`
- Create: `prompts/source_verifier.md`
- Create: `prompts/story_adapter.md`
- Create: `prompts/storyboard_director.md`

**Steps:**
1. Choose invocation method: CLI subprocess or API-compatible bridge.
2. Pass prompt + context + schema expectations explicitly.
3. Validate responses against Pydantic models.
4. Reject malformed outputs and surface retry-safe errors.

**Validation:**
- unit tests with mocked Hermes output
- `uv run pytest tests/test_workflow_smoke.py -v -k hermes`

---

### Task 7: Implement generic review-loop orchestration

**Objective:** Encode the v1 retry and best-so-far policy once.

**Files:**
- Create: `src/reel_factory/review_loop.py`
- Test: `tests/test_review_loop.py`

**Steps:**
1. Implement `run_reviewable_stage(...)`.
2. Enforce max attempts = 3.
3. Treat `overall_score > 8.0` as a clear pass.
4. Track best-so-far candidate when no clear pass occurs.
5. Return structured downgrade metadata when continuing below threshold.

**Validation:**
- `uv run pytest tests/test_review_loop.py -v`

---

### Task 8: Implement image generation pipeline

**Objective:** Generate per-scene stills using the configured visual style family.

**Files:**
- Create: `src/reel_factory/image_pipeline.py`
- Create: `prompts/image_reviewer.md`
- Test: `tests/test_workflow_smoke.py`

**Steps:**
1. Turn storyboard scenes into image prompts.
2. Call fal image generation.
3. Save request IDs, prompts, seeds, and output file paths.
4. Support regeneration at scene granularity.

**Validation:**
- mock tests for response handling
- one manual integration run against a sample storyboard

---

### Task 9: Implement shot generation pipeline

**Objective:** Generate restrained-motion clips from approved stills.

**Files:**
- Create: `src/reel_factory/video_pipeline.py`
- Create: `prompts/shot_reviewer.md`
- Test: `tests/test_workflow_smoke.py`

**Steps:**
1. Generate motion prompts from storyboard data.
2. Call fal image-to-video endpoints.
3. Explicitly discard/disable native audio from the video model.
4. Save clip metadata and source-image linkage.

**Validation:**
- mock tests for request lifecycle
- one manual integration run against a sample image

---

### Task 10: Implement dedicated audio pipeline

**Objective:** Produce narration and optional music without using video-model audio.

**Files:**
- Create: `src/reel_factory/audio_pipeline.py`
- Test: `tests/test_workflow_smoke.py`

**Steps:**
1. Generate TTS from approved narration text.
2. Add optional music layer path behind config.
3. Normalize all audio artifacts to deterministic formats.
4. Record provider/model metadata separately from video generation.

**Validation:**
- manual generation of one narration sample
- audio metadata assertions in tests

---

### Task 11: Implement OCR and deterministic text rendering

**Objective:** Render captions/source cards deterministically and verify text fidelity.

**Files:**
- Create: `src/reel_factory/ocr.py`
- Create: `src/reel_factory/assembly.py`
- Test: `tests/test_assembly.py`
- Test: `tests/test_ocr.py`

**Steps:**
1. Use Pillow to render text overlays.
2. Use FFmpeg to compose clips and overlays into a vertical timeline.
3. Run OCR on rendered frames.
4. Compare OCR output to approved strings and flag mismatches.

**Validation:**
- `uv run pytest tests/test_assembly.py tests/test_ocr.py -v`

---

### Task 12: Implement Drive archival

**Objective:** Mirror the job folder structure to Google Drive.

**Files:**
- Create: `src/reel_factory/drive.py`
- Test: `tests/test_workflow_smoke.py`

**Steps:**
1. Create run folder structure per job.
2. Upload immutable attempt folders.
3. Upload a final `manifest.json` summarizing assets, scores, and downgrade states.
4. Return Drive folder IDs/URLs.

**Validation:**
- mock Drive API tests
- one manual upload of a sample job folder

---

### Task 13: Implement Sheets tracking

**Objective:** Write one structured row per run to Google Sheets.

**Files:**
- Create: `src/reel_factory/sheets.py`
- Test: `tests/test_workflow_smoke.py`

**Steps:**
1. Define the v1 columns.
2. Add idempotent upsert by `job_id`.
3. Write attempt counts, scores, downgrade flags, Drive URL, and final status.
4. Ensure publishing fields are blank or explicit `DISABLED_V1` values.

**Validation:**
- mock Sheets API tests
- one manual row insert/update in a test sheet

---

### Task 14: Implement the top-level workflow orchestrator

**Objective:** Wire source -> script -> storyboard -> images -> clips -> audio -> assembly -> final review -> Drive -> Sheets.

**Files:**
- Create: `src/reel_factory/workflow.py`
- Test: `tests/test_workflow_smoke.py`

**Steps:**
1. Implement `run_daily_job(run_date, dry_run=False)`.
2. Use the generic review loop for all reviewable stages.
3. Ensure the v1 terminal state is `ARCHIVED_TO_DRIVE`.
4. Skip publishing entirely unless a future config explicitly enables it.

**Validation:**
- `uv run pytest tests/test_workflow_smoke.py -v`
- `uv run python -m reel_factory.cli run-daily --date 2026-07-23 --dry-run`

---

### Task 15: Add logging, runbooks, and cron readiness

**Objective:** Make the system operable daily without publishing.

**Files:**
- Create: `src/reel_factory/logging.py`
- Create: `docs/runbooks/local-run.md`
- Create: `docs/runbooks/drive-sheets-setup.md`
- Update: `README.md`

**Steps:**
1. Add structured JSON logging.
2. Document setup steps for fal, Drive, Sheets, and fonts.
3. Add a sample non-publishing cron command.
4. Add failure/debugging guidance.

**Validation:**
- run one full dry run and one full sample run
- verify log file, Drive folder, and Sheets row all exist

---

## V1 Google Sheets Columns

Use these minimum columns in v1:

- `job_id`
- `run_date`
- `status`
- `language`
- `source_family`
- `source_id`
- `quote_mode`
- `script_score`
- `storyboard_score`
- `image_score`
- `shot_score`
- `final_score`
- `source_attempts`
- `script_attempts`
- `image_attempts`
- `shot_attempts`
- `final_attempts`
- `used_best_so_far_fallback`
- `fallback_stage_list`
- `drive_folder_url`
- `final_video_path`
- `publishing_status`
- `actual_cost`
- `last_error`

Set `publishing_status = DISABLED_V1` for all normal successful runs.

---

## V1 Test Strategy

### Unit tests
- config loading
- schema validation
- review-loop scoring logic
- state-store persistence
- corpus selection filters
- OCR comparison helpers

### Mock integration tests
- Hermes adapter parsing/validation
- fal request lifecycle wrappers
- Drive upload helpers
- Sheets row upsert helpers

### End-to-end dry run
- use a tiny sample corpus
- stub model calls
- verify final state, output folder, and generated manifest

### One manual full-stack run
- real image generation
- real clip generation
- real TTS
- real Drive upload
- real Sheets update
- publishing remains disabled

---

## Risks / Tradeoffs

1. Allowing best-so-far continuation below `8.0 / 10` increases throughput but weakens strict safety.
2. Supporting all approved source families from day one increases corpus/rubric complexity.
3. No-human-review v1 means review prompts and deterministic validators must be stronger.
4. OCR fidelity on multilingual sacred references becomes more important in later phases.
5. Publishing stubs should not leak into the v1 execution path.

---

## Open Questions To Resolve Before Coding Starts

1. Which OCR library should be the primary choice in v1?
2. Should Hermes be invoked through CLI subprocesses or through another stable interface?
3. Which exact fal endpoints will be used for image, video, and TTS?
4. Should music generation be included in milestone 3 or deferred behind a feature flag?
5. What exact Google Drive folder ID and Google Sheet ID will v1 use?

---

## Definition of Done for V1

V1 is done when all of the following are true:

- A local command can run one full job end-to-end.
- The job selects only approved corpus items.
- Every reviewable stage uses the 3-attempt, `>8.0`, best-so-far policy.
- The final MP4 is assembled with deterministic overlays.
- Audio comes from a separate audio path, never the video model.
- All artifacts are uploaded to Google Drive.
- A complete tracking row is written to Google Sheets.
- Publishing is disabled by config and not triggered by the normal run path.
- The system is ready to be scheduled daily without manual intervention. Only enable after a manual PoC run is approved by the user.
