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

    args = parser.parse_args()

    if args.command == "doctor":
        print("Checking system health...")
        print(f"  Workdir: {config.get('app.workdir', 'N/A')}")
        print(f"  Language: {config.get('app.language', 'N/A')}")
        print(f"  Publishing enabled: {config.get('app.publishing_enabled', False)}")
        print(f"  Pass threshold: {config.get('review.pass_threshold', 'N/A')}")
        print(f"  Max attempts: {config.get('review.max_attempts', 'N/A')}")
        print("✅ System healthy")

    elif args.command == "run-daily":
        configure_logging()
        logger.info("cli_run_daily", date=args.date, dry_run=args.dry_run)

        workdir = config.get("app.workdir", str(Path.cwd()))
        orchestrator = WorkflowOrchestrator(workdir)

        print(f"Starting production job for {args.date} (dry_run={args.dry_run})...")
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


if __name__ == "__main__":
    main()
