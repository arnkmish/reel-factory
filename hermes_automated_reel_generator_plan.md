# Automated Faceless Short-Story Reel Generator Using Hermes

**Implementation blueprint — 23 July 2026**

> **V1 decisions locked from user clarifications — 23 July 2026**
>
> - Generate and review only for v1; **no publishing in v1**.
> - Language: **English only**.
> - Content scope: **mix of fables and scripture-based teachings**.
> - Source families in v1: **all approved source families may be used**.
> - Source-text policy: **direct quotes and paraphrases are both allowed by default**.
> - Visual direction: **minimal symbolic / spiritual**.
> - Audio policy: **use a separate audio model**; **do not use the video model's native audio**.
> - Audio default: **TTS narration + optional background music**, both configurable.
> - Storage: **Google Drive**. Tracking/reporting: **Google Sheets**.
> - Review threshold: **score must be > 8.0 / 10 to count as a clear pass**.
> - Attempts: **3 total per reviewable stage**.
> - Fallback policy: if nothing clears the threshold after 3 attempts, **continue automatically with the best-so-far candidate**.
> - Budget constraint: a single video should not cost more than **$5 USD** in fal API fees.
> - Human review: **not part of v1**.

## 1. Objective

Build a daily, fully automated pipeline that:

1. Runs every day at **07:00 Asia/Kolkata**.
2. Selects one fresh teaching, parable, moral, or ultra-short story from an approved corpus of:
   - Indian religious and philosophical texts.
   - Indian saints and teachers.
   - Other religious, philosophical, and cultural traditions.
3. Verifies the source and interpretation.
4. Converts it into a short vertical visual story.
5. Generates coherent scene artwork.
6. Animates the artwork with restrained motion.
7. Adds deterministic text, narration, music, and transitions.
8. Reviews the source, storyboard, images, shots, and final video.
9. For v1, archives and scores the final output without publishing it; later phases may publish when enabled.
10. Records every decision, asset, model call, cost, review result, and publishing URL when publishing is enabled.

The base design is safety-first, but the **locked v1 policy is score-driven rather than fail-closed**: each reviewable stage gets up to three total attempts, a score above `8.0 / 10` counts as a clear pass, and if no attempt clears the threshold the workflow should continue using the best-scoring candidate while recording the downgrade in Drive and Sheets.

---

## 2. Recommended Overall Design

Use Hermes as the reasoning and multi-agent layer, but do not ask one unconstrained agent to carry out the entire workflow conversationally.

Use four layers:

```text
Hermes cron scheduler
        |
        v
Deterministic Python workflow runner
        |
        +--> Hermes orchestrator and specialist subagents
        +--> fal image, video, and speech APIs
        +--> FFmpeg/Pillow deterministic media pipeline
        +--> Google Drive and Google Sheets
        +--> Optional YouTube and Instagram publishing APIs (disabled in v1)
        |
        v
Durable job state + logs + Sheets reporting
```

### Why this split is important

Hermes is well suited to planning, source interpretation, writing, visual direction, and multimodal review. A normal program is better suited to:

- Enforcing `max_attempts = 3`.
- Maintaining job state.
- Preventing duplicate publishing.
- Polling asynchronous model requests.
- Validating schemas.
- Running FFmpeg.
- Handling OAuth tokens.
- Retrying network calls safely.
- Calculating hashes and duplicate detection.
- Recording exact costs and model versions.

Hermes supports cron jobs, skill-backed scheduled tasks, and isolated delegated subagents. Cron executions start in fresh sessions, so the scheduled prompt and attached skill must be self-contained. [R1][R2][R3]

---

## 3. Recommended Technology Stack

### Existing services to retain

| Need | Recommended service |
|---|---|
| Agent orchestration | Hermes Agent |
| Agent hosting | Current Hostinger VPS |
| Image/video/speech inference | fal |
| Long-term media archive | Google Drive |
| Human-readable production dashboard | Google Sheets |
| Code, prompts, schemas, tests | GitHub |

### Add these components

| Component | Recommendation | Reason |
|---|---|---|
| Workflow runtime | Python 3.11+ | Strong media/API ecosystem |
| Durable state | SQLite in WAL mode initially | One job/day does not need a distributed queue |
| Scale-up state | PostgreSQL | Use only when running several channels or workers |
| Video assembly | FFmpeg and `ffprobe` | Reliable, deterministic, scriptable |
| Image compositing | Pillow | Text, gradients, masks, logos, safe areas |
| Schema validation | Pydantic | Forces agents to return structured data |
| API retries | Tenacity | Controlled transient retries |
| Google integration | `google-api-python-client`, `gspread` | Drive, Sheets, YouTube |
| fal integration | `fal-client` | Queue submission, polling, model calls |
| Logs | JSON logs with `structlog` | Searchable and machine-readable |
| Metrics | Prometheus textfile exporter or a simple metrics table | Enough for the initial volume |
| Alerts / reporting | Google Sheets first, optional Hermes alert channel later | V1 uses Sheets as the primary reporting surface |

Do not use Google Sheets as the source of truth for workflow execution. Use SQLite/PostgreSQL for state and mirror useful fields into Sheets.

---

## 4. Hostinger and Hermes Setup

### 4.1 Server prerequisites

Install:

```bash
sudo apt update
sudo apt install -y ffmpeg git fonts-noto fonts-noto-core fonts-noto-extra
```

Create a deployment directory:

```text
/opt/reel-factory/
```

Run the application through a dedicated Linux user and a `systemd` service. Do not run it as root.

### 4.2 Set the timezone explicitly

Hermes supports `HERMES_TIMEZONE` or a `timezone` field in its configuration. Set:

```bash
HERMES_TIMEZONE=Asia/Kolkata
```

Hermes resolves time from this environment variable before its config or server-local timezone. [R4]

### 4.3 Schedule

Create a Hermes cron job using the standard expression:

```text
0 7 * * *
```

The cron task should invoke one self-contained production skill or workflow command, for example:

```text
Run the reel-factory daily workflow in /opt/reel-factory.
Execute one production job for today's date.
Do not publish in v1; generate, review, archive, and update Google Drive and Google Sheets only.
Use a maximum of three total attempts per reviewable stage.
Treat a score above 8.0/10 as a clear pass, otherwise continue with the best-so-far candidate after the final attempt.
Write a final execution summary to the configured Google Sheet.
```

Prefer a skill-backed job such as `daily-reel-production` instead of placing the entire operating procedure inside the cron prompt. Test it manually with Hermes' cron run command before enabling the schedule. [R2]

### 4.4 Avoid overlap

Add a process lock:

```text
/opt/reel-factory/runtime/daily.lock
```

If yesterday's job is still running, the new job should exit with status `SKIPPED_OVERLAP` and send an alert. Do not start a second production job.

---

## 5. Repository Structure

```text
reel-factory/
├── README.md
├── pyproject.toml
├── .env.example
├── config/
│   ├── channels.yaml
│   ├── traditions.yaml
│   ├── models.yaml
│   ├── visual_styles.yaml
│   ├── review_thresholds.yaml
│   └── publishing.yaml
├── corpus/
│   ├── manifests/
│   ├── normalized/
│   └── indexes/
├── prompts/
│   ├── idea_selector.md
│   ├── source_verifier.md
│   ├── story_adapter.md
│   ├── storyboard_director.md
│   ├── image_reviewer.md
│   ├── shot_reviewer.md
│   └── final_video_reviewer.md
├── schemas/
│   ├── content_item.py
│   ├── review.py
│   ├── storyboard.py
│   └── production_job.py
├── skills/
│   └── daily-reel-production/
│       ├── SKILL.md
│       └── references/
├── src/reel_factory/
│   ├── cli.py
│   ├── orchestrator.py
│   ├── state_store.py
│   ├── corpus.py
│   ├── uniqueness.py
│   ├── fal_gateway.py
│   ├── image_pipeline.py
│   ├── video_pipeline.py
│   ├── reviewers.py
│   ├── publishers/
│   │   ├── youtube.py
│   │   └── instagram.py
│   └── integrations/
│       ├── drive.py
│       └── sheets.py
├── tests/
├── runtime/
│   ├── jobs/
│   ├── cache/
│   └── logs/
└── migrations/
```

GitHub should contain code, prompt templates, configuration, schemas, and tests. It should not contain API keys, OAuth refresh tokens, generated media, or copyrighted source dumps.

---

## 6. Content Corpus and Data Acquisition

## 6.1 Do not search the open web for a random teaching every morning

Create a curated, versioned corpus before automating publication. Each item must have:

- Stable source identifier.
- Tradition.
- Work title.
- Chapter, verse, section, sutra, page, or story identifier.
- Original-language text when legally usable.
- Approved translation.
- License and permitted use.
- Source URL.
- Quote/paraphrase status.
- Context note.
- Interpretation note.
- Sensitivity flags.
- Visual depiction constraints.
- Reviewer status.

### Canonical content record

```json
{
  "source_id": "gita-2-47-edwin-arnold",
  "tradition": "Hindu",
  "work": "Bhagavad Gita",
  "location": {"chapter": 2, "verse": 47},
  "source_language": "Sanskrit",
  "approved_translation": "...",
  "translation_author": "...",
  "license": "public-domain-or-explicit-license",
  "source_url": "...",
  "content_type": "teaching",
  "allowed_use": ["paraphrase", "short_quote"],
  "context_summary": "...",
  "interpretation_boundaries": ["..."],
  "sensitivity_flags": [],
  "depiction_policy": "symbolic-preferred",
  "verified_by": ["source-review-v1"],
  "corpus_version": "2026-07-01"
}
```

## 6.2 Initial source categories

Begin with a small, defensible corpus rather than attempting every tradition.

### Recommended Phase 1 corpus

- Bhagavad Gita.
- Selected Upanishadic teachings.
- Panchatantra and Hitopadesha.
- Jataka tales.
- Tirukkural.
- Public-domain teachings and writings of Kabir, Swami Vivekananda, Ramakrishna, and similar historical figures.
- Aesop's fables.
- Public-domain Stoic works.
- Public-domain translations of the Analects and Tao Te Ching.
- Public-domain Bible translations.
- Properly licensed Buddhist translations.

### Add later with dedicated rules

- Quran translations.
- Guru Granth Sahib translations.
- Modern saint discourses.
- Living teachers.
- Modern copyrighted commentaries.
- Traditions with strong restrictions on visual depiction.
- Oral traditions without a stable textual source.

For these, obtain explicit permission or use an API/dataset whose terms clearly permit the intended commercial or public publishing use.

## 6.3 Useful source starting points

- Project Gutenberg contains many older editions and translations, but rights must still be checked for the country of use and each individual item. Its trademark/license terms also matter when retaining Project Gutenberg branding. [R11][R12]
- SuttaCentral publishes licensing information per category and warns that some third-party legacy translations have separate rights. Do not assume everything visible on the site has identical terms. [R13]
- Quran Foundation provides developer terms for its APIs. Review and comply with those terms before storing, transforming, or publishing API-derived content. [R14]

## 6.4 Mandatory source rules

1. **Never fabricate a direct quotation.**
2. Mark every line as one of:
   - Exact quote.
   - Faithful translation.
   - Paraphrase.
   - Original moral inspired by a source.
3. Do not attach quotation marks to a paraphrase.
4. Preserve the exact chapter/verse/story identifier in internal metadata.
5. Add the source reference to the caption or final end card.
6. Do not derive teachings from unsourced quote websites.
7. Do not translate difficult sacred-language passages using an unconstrained machine translation and treat the result as authoritative.
8. When interpretations differ, use neutral language such as “One common interpretation is…”.
9. Maintain a denylist of disputed, misattributed, sectarian, inflammatory, or unverifiable sayings.
10. Use a tradition-specific review rubric.

---

## 7. Editorial Strategy

A daily generator can easily become repetitive even when the source changes. Use an editorial scheduler.

### Rotation dimensions

- Tradition.
- Source work.
- Moral theme.
- Narrative type.
- Visual style.
- Emotional tone.
- Geographic setting.
- Character type.
- Story structure.
- Language.

### Example weekly rotation

| Day | Content family |
|---|---|
| Monday | Indian scripture teaching |
| Tuesday | Indian saint teaching |
| Wednesday | Indian fable or folk wisdom |
| Thursday | Buddhist/Jain/Sikh teaching |
| Friday | Non-Indian religious or philosophical teaching |
| Saturday | Global fable or philosopher |
| Sunday | Reflective synthesis, without falsely merging doctrines |

The scheduler should be configurable and should not reduce a tradition to a token quota. The purpose is editorial variety and duplicate prevention.

### Idea selection process

1. Retrieve 10 eligible corpus items.
2. Exclude anything used or semantically similar to the previous 90 days.
3. Generate three possible short-form treatments for each.
4. Score on:
   - Source confidence.
   - Clarity.
   - Emotional resonance.
   - Visual potential.
   - Novelty.
   - Cultural risk.
   - Suitability for 20–45 seconds.
5. Select the highest-scoring candidate that passes all blocking rules.

Store rejected candidates and reasons so they are not reconsidered repeatedly.

For locked v1 behavior, this selection step may draw from **all approved source families** rather than a narrower bootstrap whitelist, but each item must still satisfy licensing, verification, and sensitivity rules.

---

## 8. Multi-Agent Structure

Use one parent orchestrator and specialist subagents. Hermes subagents have isolated context, making them useful for independent review. Only their final summaries return to the parent, so require strict JSON outputs. [R3]

## 8.1 Agent roles

### A. Production Orchestrator

Responsibilities:

- Loads the current job state.
- Calls each workflow stage.
- Dispatches specialist agents.
- Enforces attempt limits.
- Accepts only schema-valid outputs.
- Moves the job to `PUBLISHED`, `QUARANTINED`, or `FAILED`.
- Never edits source claims itself.

### B. Corpus Retriever and Idea Selector

Responsibilities:

- Retrieves approved source items.
- Checks recent-history similarity.
- Proposes treatments.
- Returns evidence and source IDs.

### C. Source and Interpretation Reviewer

Responsibilities:

- Verifies source identifier and wording.
- Distinguishes quote from paraphrase.
- Checks contextual faithfulness.
- Flags sectarian or depiction risks.
- Does not optimize for virality.

Use a different model or at least a fresh isolated context from the writer.

### D. Story Adapter

Responsibilities:

- Converts the selected teaching into a 20–45 second script.
- Produces hook, scene text, optional narration, moral, source card, and caption.
- Uses simple language without changing the doctrine.
- Avoids preachy, manipulative, or sensational claims.

### E. Storyboard and Visual Director

Responsibilities:

- Converts the approved script into 5–8 shots.
- Maintains character, setting, palette, symbols, and chronology.
- Produces clean image prompts with **no embedded text**.
- Produces minimal-motion prompts separately.

### F. Image Generation Worker

Responsibilities:

- Calls the configured fal image endpoint.
- Uses style references, character sheets, seeds, and negative prompts.
- Saves raw output and generation metadata.

### G. Image and Cohesion Reviewer

Responsibilities:

- Reviews each image and the complete image set.
- Checks prompt compliance, continuity, anatomy, objects, symbolism, cultural appropriateness, visual hierarchy, and safe areas.
- Returns localized regeneration instructions.

### H. Motion and Shot Worker

Responsibilities:

- Calls an image-to-video endpoint for approved scenes.
- Uses restrained movement prompts.
- Saves model request IDs, seeds, outputs, and cost.

### I. Shot Reviewer

Responsibilities:

- Reviews start, middle, and end frames plus motion summary.
- Checks identity drift, warping, flicker, sudden camera movement, distorted symbols, unwanted text, and unsafe content.

### J. Assembly and Typography Worker

This should mostly be deterministic code, not an LLM.

Responsibilities:

- Normalizes clips.
- Applies transitions.
- Adds text overlays.
- Adds narration, subtitles, logo, source card, and music.
- Exports final variants.

### K. Final Video Reviewer

Responsibilities:

- Reviews sampled frames or the full video through a video-capable vision model.
- Checks story coherence, chronology, readability, pacing, factual faithfulness, audio, and ending.
- Verifies that the final moral matches the approved script.

### L. Publisher and Analytics Worker

Responsibilities:

- Generates platform-specific metadata.
- Publishes idempotently.
- Stores platform IDs.
- Pulls later performance metrics for feedback.

---

## 9. Daily State Machine

```text
NEW
  -> SOURCE_SELECTED
  -> SOURCE_APPROVED
  -> SCRIPT_APPROVED
  -> STORYBOARD_APPROVED
  -> IMAGES_APPROVED
  -> SHOTS_APPROVED
  -> ASSEMBLED
  -> FINAL_APPROVED
  -> ARCHIVED_TO_DRIVE
  -> UPLOADED_PRIVATE
  -> PUBLISHED
```

For v1, the terminal success state is `ARCHIVED_TO_DRIVE`. `UPLOADED_PRIVATE` and `PUBLISHED` remain later-phase states.

Failure states:

```text
RETRYABLE
QUARANTINED
FAILED_INFRASTRUCTURE
SKIPPED_OVERLAP
SKIPPED_NO_ELIGIBLE_SOURCE
```

### Attempt rule

For every generative stage with a review loop:

```python
MAX_ATTEMPTS = 3  # includes the initial generation
```

Scoring rule:

```python
PASS_THRESHOLD = 8.0
```

Example:

```python
best_artifact = None
best_review = None

for attempt in range(1, MAX_ATTEMPTS + 1):
    artifact = generate(previous_feedback)
    review = review_artifact(artifact)

    if best_review is None or review.overall_score > best_review.overall_score:
        best_artifact = artifact
        best_review = review

    if review.pass_ and review.overall_score > PASS_THRESHOLD:
        approve(artifact)
        break

    if attempt == MAX_ATTEMPTS:
        approve_with_downgrade(best_artifact, best_review)
    else:
        previous_feedback = review.fix_instructions
```

Do not interpret “three attempts” as an initial attempt plus three retries. The maximum is three total generations for that stage.

For v1, `approve_with_downgrade(...)` means: continue with the best-scoring artifact, record that it did not clear `8.0 / 10`, and surface the reason in Drive and Sheets.

### Retry classification

- **Content failure:** regenerate using reviewer instructions.
- **Transient API failure:** exponential backoff; does not consume a creative review attempt unless an artifact was produced.
- **Policy/safety failure:** block immediately or regenerate with a stricter prompt.
- **Source uncertainty:** quarantine; do not paraphrase around the uncertainty.
- **Publishing API failure:** retry idempotently using the stored upload/container ID.

---

## 10. Structured Review Contract

Every reviewer must return JSON matching:

```json
{
  "pass": false,
  "overall_score": 7.4,
  "score_scale": 10,
  "clear_pass_threshold": 8.0,
  "blocking_issues": [
    {
      "code": "SOURCE_CONTEXT_LOST",
      "severity": "blocking",
      "location": "scene_4",
      "evidence": "The script changes duty without attachment into guaranteed material success.",
      "fix": "Rewrite the outcome without promising worldly reward."
    }
  ],
  "non_blocking_issues": [],
  "dimension_scores": {
    "source_faithfulness": 6.0,
    "coherence": 9.0,
    "clarity": 8.2,
    "cultural_sensitivity": 9.5
  },
  "fix_instructions": [
    "Replace the final moral with a source-faithful statement."
  ],
  "reviewer_model": "...",
  "review_prompt_version": "source-review-v3"
}
```

### Review design principles

- Reviewer sees the source passage and approved context.
- Reviewer does not see the writer's hidden reasoning.
- Reviewer must cite exact scene IDs and evidence.
- “Looks good” is not a valid review.
- A score cannot override a blocking issue.
- A second model family is preferable for review.
- Use deterministic validators before asking an LLM/VLM.
- The reviewer must emit both a boolean `pass` and a numeric score so the workflow can distinguish a clear pass from a best-so-far fallback.

---

## 11. Stage-by-Stage Workflow

## 11.1 Source selection gate

### Inputs

- Corpus manifest.
- Previous 90–180 days of published items.
- Editorial rotation.
- Channel language.
- Target duration.

### Automated checks

- License permits use.
- Source is verified.
- No unresolved sensitivity flags.
- Not previously used.
- Embedding similarity below configured threshold.
- Enough context exists to avoid a misleading extract.

### Pass criteria

- Source confidence: 100%.
- License field present.
- Stable source locator present.
- Novelty score above threshold.
- Cultural risk below threshold or covered by specific rules.

---

## 11.2 Script gate

Recommended output:

```json
{
  "title": "...",
  "hook": "...",
  "duration_seconds": 32,
  "quote_mode": "paraphrase",
  "scenes": [
    {
      "scene_id": "S01",
      "duration": 4,
      "screen_text": "...",
      "narration": "...",
      "story_function": "hook"
    }
  ],
  "final_moral": "...",
  "source_credit": "...",
  "caption": "...",
  "hashtags": ["..."]
}
```

### Writing constraints

- 5–8 scenes.
- 20–45 seconds initially.
- One central idea.
- Hook in the first 1–1.5 seconds.
- Approximately 6–12 on-screen words per scene.
- Short sentences.
- No fabricated dialogue presented as scripture.
- No claim such as “This guarantees success”.
- No attack on another belief.
- No guilt, fear, or miracle-based engagement bait.
- Source credit on end card and caption.

### Review criteria

- Faithfulness.
- Completeness.
- Clear causal sequence.
- No contradiction across scenes.
- Moral follows from the story.
- Language is understandable without prior religious knowledge.
- No misleading quotation marks.
- No forced controversy.

---

## 11.3 Storyboard gate

Each scene should contain:

```json
{
  "scene_id": "S03",
  "visual_description": "...",
  "characters": ["traveller_v1"],
  "setting": "forest_path_dawn",
  "composition": "...",
  "camera": "medium-wide",
  "palette": ["saffron", "forest green", "warm grey"],
  "symbols": ["unlit_lantern"],
  "image_prompt": "...",
  "negative_prompt": "...",
  "motion_prompt": "Very slow push-in; leaves move subtly; no facial movement.",
  "text_safe_zone": "upper_center",
  "depiction_notes": ["Do not depict a named prophet or saint."]
}
```

### Visual consistency package

Create once per reel:

- Character sheet.
- Clothing specification.
- Setting bible.
- Palette.
- Lighting.
- Illustration style.
- Symbol glossary.
- Fixed aspect ratio.
- Reference image IDs.
- Seed strategy.

For recurring channel identity, define 3–5 approved visual families instead of using one template forever.

---

## 11.4 Image generation

### Recommended fal options

Keep endpoints configurable because model quality, prices, and availability change.

Possible roles:

- High-quality prompt-following or reference-conditioned image generation.
- Image editing for continuity fixes.
- Character/reference preservation.
- Vertical 9:16 output.

For example, fal exposes FLUX Kontext endpoints for generation/editing and reference consistency. [R6][R7]

### Generation method

1. Generate a master character/style reference when needed.
2. Generate one candidate per scene.
3. Review the full set.
4. Regenerate only failed scenes where possible.
5. If a continuity change affects later scenes, invalidate dependent scenes.
6. Save:
   - Endpoint.
   - Model version.
   - Prompt.
   - Negative prompt.
   - Seed.
   - Request ID.
   - Output URL.
   - Local/Drive hash.
   - Cost.

### Important typography rule

Do not ask the image model to render final captions. Even capable typography models can introduce spelling changes, and the subsequent video model may deform the text.

Generate clean art, animate it, and overlay text afterward with Pillow/FFmpeg.

---

## 11.5 Image review

Use a vision-capable reviewer with both:

- Individual scene prompt.
- Contact sheet of all scenes.
- Character/style reference.

### Blocking checks

- Wrong number or identity of characters.
- Inconsistent clothing, age, symbols, or setting.
- Incorrect event or chronology.
- Accidental religious symbols from another tradition.
- Unapproved deity, prophet, or saint depiction.
- Extra limbs or severe anatomy defects.
- Gibberish or unwanted text.
- Sexualized or violent imagery not justified by the source.
- Poor text-safe area.
- Near-duplicate composition across most scenes.

### Recommended pass thresholds

- Scene compliance: at least 90/100.
- Cross-scene cohesion: at least 85/100.
- Cultural sensitivity: no blocking issue.
- Technical quality: no severe artifact.

---

## 11.6 Image-to-video animation

fal supports asynchronous model APIs and image-to-video endpoints. Current examples include Kling Video and Wan image-to-video models. [R5][R8][R9]

### Recommended production modes

#### Mode A: Hybrid, recommended

- Use generated image-to-video for 1–3 visually important shots.
- Use deterministic Ken Burns, parallax, particle, lighting, or depth motion for the remaining shots.

Advantages:

- Lower cost.
- Fewer identity-drift failures.
- Better text stability.
- Faster production.
- Less repetitive AI motion.

#### Mode B: All shots through image-to-video

Use when the requirement is that every image be model-animated. Keep motion restrained and overlay text only afterward.

### Minimal-motion prompt pattern

```text
Preserve the source image exactly.
Very slow camera push-in.
Only subtle cloth, foliage, candlelight, dust, or water movement.
No new characters or objects.
No face transformation.
No lip movement.
No scene cut.
No camera shake.
No text.
Maintain composition and vertical framing.
```

### Clip rules

- 3–6 seconds per shot.
- 9:16.
- No native generated speech unless explicitly needed.
- Do not use the video model's generated audio track.
- Use a separate speech or music model when audio is needed.
- Keep the first and last frame visually close to the source.
- Store the source image alongside the generated clip.

---

## 11.7 Shot review

For each clip:

1. Extract frames at:
   - 0%.
   - 25%.
   - 50%.
   - 75%.
   - 100%.
2. Create a contact sheet.
3. Run deterministic checks.
4. Run VLM review.

### Deterministic checks

- Expected duration.
- Valid codec and resolution.
- No decode error.
- No black frames.
- No frozen output unless intended.
- No unexpected aspect-ratio crop.
- Motion magnitude within limit.
- Perceptual similarity to source image remains above threshold.

### VLM checks

- Character identity preserved.
- Symbols preserved.
- No morphing.
- No new objects.
- No unwanted text.
- Motion matches “minimal”.
- No inappropriate facial or body movement.
- No temporal contradiction.

Regenerate the shot only. Do not regenerate all shots unless the shared style reference is the problem.

---

## 11.8 Typography, narration, and assembly

### Canvas

- Master: `1080 x 1920`.
- Frame rate: 30 fps.
- Video: H.264.
- Audio: AAC.
- Keep essential text and faces away from platform UI areas.

### Text system

Use deterministic templates with:

- Noto font families for Indian scripts.
- High contrast.
- Gradient or translucent backing.
- Maximum 2–3 text lines.
- Automatic font fitting.
- Word-safe line breaking.
- Language-specific punctuation.
- End card with source and channel identity.

Run OCR on rendered frames and compare recognized text to the approved source string. For multilingual use, configure language-specific OCR packs. Treat any mismatch in sacred quotes or source identifiers as blocking.

### Narration

Narration is optional but recommended for retention and accessibility.

Use a neutral voice. Do not:

- Clone a living teacher without consent.
- Imitate a saint or religious leader.
- Claim the voice is authentic.
- Put invented words into the mouth of a named figure.

fal provides speech-generation endpoints; keep the provider configurable. [R10]

For locked v1 behavior, narration should use a **dedicated TTS/audio model**. Do not rely on any video model's bundled or default audio generation.

### Music

Use:

- Original music.
- Properly licensed royalty-free music.
- A subscription library whose license covers automated social publishing.

Do not download trending platform audio and reuse it outside its license. API publishing to Instagram also cannot be assumed to add licensed music automatically.

### Loudness targets

Use practical short-form targets, for example:

- Integrated loudness around `-14 to -16 LUFS`.
- True peak below `-1 dBTP`.
- Duck music under narration.
- Avoid abrupt silence or clipping.

---

## 11.9 Final video review

### Inputs

- Approved source record.
- Approved script.
- Final MP4.
- Transcript.
- Extracted frame contact sheet.
- `ffprobe` output.
- OCR report.
- Audio analysis.

### Blocking checks

- Final words differ from approved script.
- Quote or source reference is wrong.
- Scene order is wrong.
- Moral is missing or contradicted.
- Text is clipped or unreadable.
- Visual contains a disallowed depiction.
- Narration mispronounces a central name or term.
- Audio is missing, clipped, or badly out of sync.
- Video specification is invalid.
- Watermark or generated-model branding is present.
- A scene contains obvious distortion.
- Reel is substantially similar to a recent reel.
- AI disclosure metadata/caption configuration is missing when required.

Only `FINAL_APPROVED` jobs may enter the publishing worker.

---

## 12. Publishing

Publishing remains part of the long-term design, but it is **disabled in locked v1**. The v1 workflow should still keep the publishing interfaces and metadata contracts clean so later phases can enable them without redesigning the state model.

## 12.1 Publish private first

Recommended sequence:

1. Upload YouTube video as `private`.
2. Create Instagram media container but do not publish yet, or publish first only after final API validation.
3. Confirm platform processing succeeds.
4. Publish or schedule according to the channel configuration.
5. Store immutable platform IDs.

This provides a final infrastructure check without exposing failed media.

## 12.2 YouTube Shorts

Use the YouTube Data API `videos.insert` endpoint with OAuth. It supports upload metadata including `status.containsSyntheticMedia`. New unverified API projects can have uploads restricted to private until the project passes Google's audit, so complete that process before production launch. [R15]

Set, as applicable:

```json
{
  "status": {
    "privacyStatus": "private",
    "containsSyntheticMedia": true,
    "selfDeclaredMadeForKids": false
  }
}
```

Do not mark content “not made for kids” automatically if the actual channel is directed at children. Make a deliberate channel-level decision.

YouTube requires original and authentic content for monetization and identifies mass-produced, repetitive, or generic content as inauthentic. A daily automated slideshow using the same template, music, structure, and wording is a monetization risk even when every source passage differs. [R16]

YouTube also requires disclosure when realistic content is meaningfully generated or altered with AI. Disclosing AI use does not itself make a video ineligible for monetization. [R17]

## 12.3 Instagram Reels

Use the official Instagram API for a Professional account. The official Meta Postman collection documents the server-publishing flow:

1. Create a Reel media container using a publicly accessible `video_url`.
2. Poll container status.
3. Publish using `media_publish`.

The source video URL must be reachable by Meta. A short-lived signed URL or temporary object-storage URL is preferable to exposing the whole Drive folder. [R18]

Create a dedicated Meta app, configure OAuth/token refresh, and request the required publishing permissions. Keep the API version configurable and review Meta's current documentation before deployment.

## 12.4 Idempotency

Generate a stable publishing key:

```text
sha256(channel_id + source_id + script_version + final_video_hash)
```

Before publishing, check whether that key already has a platform ID. Never publish the same key twice.

---

## 13. Google Drive Layout

```text
ReelFactory/
├── corpus/
├── production/
│   └── 2026/
│       └── 07/
│           └── 2026-07-23_<job-id>/
│               ├── 00_source/
│               ├── 01_script/
│               ├── 02_storyboard/
│               ├── 03_images_raw/
│               ├── 04_images_approved/
│               ├── 05_clips_raw/
│               ├── 06_clips_approved/
│               ├── 07_audio/
│               ├── 08_final/
│               ├── 09_reviews/
│               └── manifest.json
├── published/
└── quarantined/
```

Do not overwrite previous attempts. Use immutable attempt folders:

```text
scene_S03/attempt_01/
scene_S03/attempt_02/
scene_S03/attempt_03/
```

---

## 14. Google Sheet Design

Create one row per production job.

### Essential columns

```text
job_id
run_date
channel
language
tradition
source_work
source_locator
source_id
quote_or_paraphrase
license
idea_title
theme
script_version
scene_count
image_model
video_model
tts_model
source_review_score
script_review_score
image_review_score
shot_review_score
final_review_score
source_attempts
script_attempts
image_attempts
shot_attempts
final_attempts
status
quarantine_reason
estimated_cost
actual_cost
drive_folder_url
final_video_url
youtube_video_id
youtube_url
instagram_media_id
instagram_url
published_at
views_24h
avg_view_duration
completion_rate
likes
comments
shares
saves
last_error
prompt_bundle_version
corpus_version
```

Use controlled dropdowns and conditional formatting, but do not rely on sheet cells for exclusive locks or retries.

---

## 15. Model Configuration Strategy

Create `config/models.yaml`:

```yaml
image:
  primary:
    endpoint: fal-ai/...
    role: high_quality_vertical_generation
  edit:
    endpoint: fal-ai/...
    role: continuity_fixes

video:
  primary:
    endpoint: fal-ai/...
    role: restrained_image_to_video
  economical:
    endpoint: fal-ai/...
    role: low_cost_fallback

speech:
  primary:
    endpoint: fal-ai/...
    role: multilingual_narration

review:
  source_model: provider/model-a
  vision_model: provider/model-b
  final_video_model: provider/model-c
```

Do not hard-code one model in prompts or business logic. Record the exact endpoint and version in every job manifest.

### Selection policy

- Primary model for final production.
- Cheaper model for prototypes or non-hero scenes.
- Different model family for review where practical.
- Monthly benchmark using a fixed test set.
- Promote a model only after it passes source consistency, visual consistency, motion restraint, latency, and cost tests.

---

## 16. Cultural and Religious Safety Rules

This category requires stricter controls than generic motivational content.

### Mandatory rules

- Prefer symbolic visual treatment when depiction is sensitive.
- Maintain tradition-specific “do not depict” rules.
- Do not anthropomorphize or visually impersonate a revered figure without an approved policy.
- Do not create fake historical footage.
- Do not use a photorealistic living teacher without permission.
- Do not synthesize the voice of a living or historical religious figure.
- Do not collapse distinct traditions into “all religions say the same thing”.
- Do not assign modern political positions to a scripture or saint.
- Do not use sacred material as a joke, meme, rage bait, or engagement trap.
- Avoid graphic violence even when the source story contains it; use symbolic framing.
- Include a correction and takedown process.
- Store the exact source evidence for every published claim.
- Allow a tradition or source to be permanently blocked after an incident.

### Automatic-publish policy

Use three risk tiers:

| Tier | Example | Action |
|---|---|---|
| Low | Public-domain fable with clear moral | Eligible for automatic publication |
| Medium | Scripture paraphrase with established context | Automatic only after strong source review |
| High | Disputed doctrine, living teacher, sensitive depiction, interfaith comparison | Quarantine for human approval |

A fully autonomous channel should initially publish only low-risk and carefully defined medium-risk items.

---

## 17. Success Criteria

## 17.1 Operational

- At least 95% of scheduled jobs start within five minutes of 07:00.
- No duplicate publications.
- 100% of jobs have complete manifests.
- 100% of generated assets have hashes and model metadata.
- Fewer than 5% fail due to infrastructure after stabilization.
- Every failed job produces a useful alert and resumable state.

## 17.2 Source quality

- 100% of videos have a stable source locator.
- 100% of quotes match the approved source exactly.
- 0 fabricated quotations.
- 0 unlicensed translations knowingly published.
- 100% of paraphrases are labeled internally and not presented as direct quotations.
- Corrections can be traced to source, prompt, model, and reviewer version.

## 17.3 Visual and video quality

- No clipped text.
- OCR match of approved on-screen text: 100% for source quotations and references.
- No blocking image or motion artifact.
- Cross-scene identity/visual cohesion score at least 85/100.
- Final technical validation passes on every published file.
- Video remains understandable without sound.
- Narration, when used, remains understandable without reading.

## 17.4 Originality and platform fitness

- No near-duplicate story treatment within 90 days.
- No repeated template across most recent posts.
- At least three rotating visual systems.
- Variation in hook, narrative pattern, pacing, and shot composition.
- Every post contains meaningful original adaptation, visual direction, and editing.
- AI disclosure is set when required.

## 17.5 Audience metrics

Establish baselines after the first 30 posts, then optimize for:

- Three-second hold rate.
- Average percentage viewed.
- Completion rate.
- Rewatch rate.
- Shares per 1,000 views.
- Saves per 1,000 views.
- Meaningful comments rather than only likes.
- Follower conversion per 1,000 views.

Do not let the analytics agent optimize toward controversy, fear, sectarian conflict, or misinformation.

## 17.6 Cost

Track:

- Cost per generated scene.
- Cost per approved scene.
- Cost per approved shot.
- Cost per published reel.
- Cost lost to quarantined attempts.
- Reviewer token cost.
1322| - Storage and egress. Max cost per reel: $5.00.

fal prices vary by model and can change. Current model pages expose per-image, per-second, or per-request pricing; treat any estimate as a configuration value, not a permanent assumption. [R5][R6][R8][R9][R10]

---

## 18. Analytics Feedback Loop

Run a separate weekly Hermes job, not inside the daily production critical path.

### Inputs

- Performance metrics.
- Source category.
- Hook type.
- Scene count.
- Duration.
- Text density.
- Narration status.
- Visual style.
- Animation model.
- Posting time.
- Review scores.

### Outputs

- Which combinations improve retention.
- Which themes cause negative or corrective comments.
- Which visual styles feel repetitive.
- Which pronunciation or translation issues recur.
- Recommendations for the next week's editorial mix.

The analytics agent may change configurable preferences, but it must not alter source-faithfulness rules or safety thresholds.

---

## 19. Monitoring and Alerts

Record in Sheets and optionally alert later on:

- Cron did not run.
- Lock overlap.
- No eligible source.
- Three-attempt downgrade to best-so-far.
- Source reviewer disagreement.
- fal request stuck or failed.
- Drive upload failure.
- Sheet logging failure.
- OAuth/token expiry.
- YouTube upload restricted to private.
- Instagram container failed.
- Duplicate-key detection.
- Final video technical failure.
- Daily cost exceeds budget.

Daily Sheets summary should include:

```text
Job:
Source:
Status:
Duration:
Scenes:
Models:
Review scores:
Attempts:
Cost:
Drive folder:
YouTube:
Instagram:
Warnings:
```

---

## 20. Security and Reliability

- Store secrets in environment variables or a secrets manager.
- Use separate OAuth credentials for development and production.
- Restrict Google Drive permissions.
- Never expose refresh tokens in Sheets or logs.
- Redact source API keys from Hermes tool output.
- Give subagents only the tools required for their role.
- Run media-processing commands with fixed argument builders, not unsanitized shell strings.
- Validate all downloaded media MIME types and sizes.
- Use signed temporary URLs for Instagram publishing.
- Back up the SQLite database and configuration daily.
- Pin Python dependencies.
- Pin prompt and schema versions.
- Keep an immutable audit record for published jobs.
- Add a global `PUBLISHING_ENABLED=false` kill switch.
- Add per-platform kill switches.
- Add a daily budget ceiling.

---

## 21. Implementation Phases

## Phase 1: Offline proof of concept

Scope:

- One language.
- All approved source families, subject to corpus approval status.
- Five-scene videos.
- No automatic publishing.
- Generate locally and save to Drive.
- No human review in the critical path.

Exit criteria:

- 20 consecutive source-faithful scripts.
- 90%+ image-set approval within two attempts.
- No text errors after deterministic overlay.
- Stable final-video generation.

## Phase 2: Controlled automation

Scope:

- Hermes cron at 07:00.
- Full state machine.
- Automated reviews.
- Upload disabled; archive to Drive and log to Sheets only.
- Instagram publishing disabled.
- No human review in the critical path.

Exit criteria:

- 14 consecutive successful daily runs.
- No duplicate upload.
- No three-attempt rule violation.
- Complete audit records.

## Phase 3: Low-risk auto-publishing

Scope:

- Automatic publishing for whitelisted low-risk content.
- High-risk content quarantined.
- YouTube and Instagram enabled.
- Alerts and kill switch active.

Exit criteria:

- 30 published reels with no material correction.
- Stable API tokens and idempotency.
- Platform processing success above 98%.

## Phase 4: Scale and optimization

Scope:

- More languages.
- More traditions.
- Multiple channels.
- Model benchmarking.
- Weekly analytics.
- PostgreSQL and worker queue only if volume justifies them.

---

## 22. First Production Configuration

A practical first version:

```yaml
schedule:
  cron: "0 7 * * *"
  timezone: "Asia/Kolkata"

content:
  language: "English"
  duration_seconds:
    min: 24
    max: 40
  scenes:
    min: 5
    max: 7
  source_whitelist:
    - "*approved_source_families"
  high_risk_auto_publish: false
  similarity_window_days: 90
  quote_modes_allowed:
    - direct_quote
    - paraphrase
  visual_family: "minimal_symbolic_spiritual"

attempts:
  source: 3
  script: 3
  images: 3
  shots: 3
  final_video: 3

publishing:
  upload_youtube_private_first: false
  instagram_enabled: false
  global_enabled: false

audio:
  use_video_model_audio: false
  narration:
    enabled: true
    provider_mode: configurable
  music:
    enabled: optional
    provider_mode: configurable

review:
  pass_threshold: 8.0
  fallback_on_threshold_miss: best_so_far
  human_review_enabled: false

video:
  width: 1080
  height: 1920
  fps: 30
  codec: h264
  text_after_animation: true
```

Start with publishing disabled. V1 ends at Drive archival plus Sheets logging. Later phases can enable YouTube private uploads, then public YouTube, then Instagram.

---

## 23. Core Workflow Pseudocode

```python
def run_daily_job(run_date):
    job = state.create_or_resume(run_date)
    lock.acquire_or_exit()

    try:
        candidate = run_stage(
            "source",
            max_attempts=3,
            generate=select_source,
            review=review_source,
        )

        script = run_stage(
            "script",
            max_attempts=3,
            generate=lambda feedback: adapt_story(candidate, feedback),
            review=lambda value: review_script(candidate, value),
        )

        storyboard = run_stage(
            "storyboard",
            max_attempts=3,
            generate=lambda feedback: create_storyboard(script, feedback),
            review=lambda value: review_storyboard(candidate, script, value),
        )

        images = generate_and_review_scenes(
            storyboard=storyboard,
            max_attempts_per_scene=3,
            set_review=True,
        )

        clips = animate_and_review_scenes(
            images=images,
            storyboard=storyboard,
            max_attempts_per_scene=3,
        )

        final_video = assemble_deterministically(
            clips=clips,
            script=script,
            add_text_after_animation=True,
        )

        final_review = run_stage(
            "final_video",
            max_attempts=3,
            generate=lambda feedback: revise_assembly(final_video, feedback),
            review=lambda value: review_final_video(
                source=candidate,
                script=script,
                video=value,
            ),
        )

        mirror_to_drive_and_sheet(job)
        if config.publishing.global_enabled:
            publishing_key = compute_idempotency_key(job, final_review.artifact)
            upload_private_and_validate(publishing_key, final_review.artifact)
            publish_to_enabled_platforms(publishing_key)
        state.complete(job)

    except QuarantineRequired as error:
        state.quarantine(job, error)
        mirror_to_drive_and_sheet(job)
        alert(error)

    finally:
        lock.release()
```

---

## 24. Final Recommendations

1. Treat this as a media production system, not a single prompt.
2. Use Hermes cron and delegation, but keep state and retries in deterministic code.
3. Curate and license the corpus before daily generation.
4. Require exact source evidence for every published reel.
5. Generate artwork without captions; add text after animation.
6. Use a different reviewer context/model from the generator.
7. Count the initial generation as attempt one; stop after attempt three.
8. For locked v1, record score downgrades and continue with the best-so-far candidate after three attempts; later phases can restore stricter quarantine behavior if desired.
9. Begin with low-risk stories and fables before sensitive scripture interpretations.
10. Vary visual language and narrative structure to avoid mass-produced, repetitive output.
11. Keep publishing disabled in v1, then upload privately and validate before any public publishing in later phases.
12. Preserve a complete audit trail and an immediate publishing kill switch.

---

## References

- **[R1] Hermes Agent repository and capabilities:** https://github.com/NousResearch/hermes-agent
- **[R2] Hermes cron automation guide:** https://github.com/NousResearch/hermes-agent/blob/main/website/docs/guides/automate-with-cron.md
- **[R3] Hermes subagent delegation:** https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/delegation.md
- **[R4] Hermes timezone implementation:** https://github.com/NousResearch/hermes-agent/blob/main/hermes_time.py
- **[R5] fal documentation:** https://fal.ai/docs/documentation
- **[R6] FLUX Kontext image editing on fal:** https://fal.ai/models/fal-ai/flux-pro/kontext
- **[R7] FLUX Kontext text-to-image API:** https://fal.ai/models/fal-ai/flux-pro/kontext/text-to-image/api
- **[R8] Kling Video v3 image-to-video API:** https://fal.ai/models/fal-ai/kling-video/v3/standard/image-to-video/api
- **[R9] Wan image-to-video API:** https://fal.ai/models/fal-ai/wan/v2.7/image-to-video/api
- **[R10] MiniMax Speech 2.8 HD on fal:** https://fal.ai/models/fal-ai/minimax/speech-2.8-hd/api
- **[R11] Project Gutenberg license:** https://www.gutenberg.org/policy/license.html
- **[R12] Project Gutenberg Bhagavad Gita example:** https://www.gutenberg.org/files/2388/2388-h/2388-h.htm
- **[R13] SuttaCentral licensing:** https://suttacentral.net/licensing
- **[R14] Quran Foundation developer terms:** https://api-docs.quran.com/legal/developer-terms/
- **[R15] YouTube Data API `videos.insert`:** https://developers.google.com/youtube/v3/docs/videos/insert
- **[R16] YouTube channel monetization policies:** https://support.google.com/youtube/answer/1311392
- **[R17] YouTube AI/synthetic-content disclosure:** https://support.google.com/youtube/answer/14328491
- **[R18] Official Meta Instagram API Postman documentation:** https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api
