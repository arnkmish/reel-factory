"""
Reel Factory CLI — entry point for all commands.
"""
import argparse
import sys
from pathlib import Path

from reel_factory.config import config
from reel_factory.workflow import WorkflowOrchestrator
from reel_factory.logging import configure_logging, get_logger

logger = get_logger("cli")


def main():
    parser = argparse.ArgumentParser(description="Reel Factory CLI")
    subparsers = parser.add_subparsers(dest="command")

    # doctor
    subparsers.add_parser("doctor", help="Check system health and configuration")

    # run-daily
    run_parser = subparsers.add_parser("run-daily", help="Execute the daily production job")
    run_parser.add_argument("--date", type=str, required=True, help="Job date (YYYY-MM-DD)")
    run_parser.add_argument("--dry-run", action="store_true", help="Simulate run without API calls")
    run_parser.add_argument("--source-id", type=str, default=None, help="Force a specific corpus source ID")
    run_parser.add_argument("--workdir", type=str, default=None, help="Override working directory")

    args = parser.parse_args()

    if args.command == "doctor":
        print("Checking system health...")
        print(f"  Project root: {config.root}")
        print(f"  Workdir: {config.workdir}")
        print(f"  Runtime dir: {config.runtime_dir}")
        print(f"  Language: {config.get('app.language', 'N/A')}")
        print(f"  Publishing enabled: {config.get('app.publishing_enabled', False)}")
        print(f"  TTS backend: {config.get('app.tts.backend', 'N/A')}")
        print(f"  TTS voice: {config.get('app.tts.voice', 'N/A')}")
        print(f"  Character consistency: {config.get('app.image.character_consistency', 'N/A')}")
        print(f"  Pass threshold: {config.get('review.pass_threshold', 'N/A')}")
        print(f"  Max attempts: {config.get('review.max_attempts', 'N/A')}")
        print(f"  FAL_KEY set: {'yes' if config.env.get('FAL_KEY') else 'no'}")
        print(f"  Hermes available: {'yes' if _check_hermes() else 'no'}")
        print(f"  FFmpeg available: {'yes' if _check_ffmpeg() else 'no'}")
        print(f"  ffprobe available: {'yes' if _check_ffprobe() else 'no'}")
        print("✅ System healthy")

    elif args.command == "run-daily":
        configure_logging()
        logger.info("cli_run_daily", date=args.date, dry_run=args.dry_run)

        # Use --workdir flag, then config, then CWD
        if args.workdir:
            workdir = args.workdir
        else:
            workdir = str(config.workdir)

        orchestrator = WorkflowOrchestrator(workdir)

        print(f"Starting production job for {args.date} (dry_run={args.dry_run})...")
        print(f"  Workdir: {workdir}")
        job = orchestrator.run_daily(args.date, dry_run=args.dry_run, source_id=args.source_id)

        print(f"\n✅ Job complete:")
        print(f"   Job ID: {job.job_id}")
        print(f"   Status: {job.status.value}")
        print(f"   Source: {job.source.corpus_item.source_id if job.source else 'N/A'}")
        print(f"   Total cost: ${job.total_cost:.2f}")
        print(f"   Drive folder: {job.drive_folder_url or 'N/A'}")
        print(f"   Final video: {job.final_video_path or 'N/A'}")
        print(f"   Sheets updated: {job.sheets_row_updated}")

    else:
        parser.print_help()


def _check_hermes() -> bool:
    """Check if hermes CLI is available."""
    import shutil
    return shutil.which("hermes") is not None


def _check_ffmpeg() -> bool:
    """Check if ffmpeg is available."""
    import shutil
    return shutil.which("ffmpeg") is not None


def _check_ffprobe() -> bool:
    """Check if ffprobe is available."""
    import shutil
    return shutil.which("ffprobe") is not None


if __name__ == "__main__":
    main()