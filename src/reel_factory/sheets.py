"""
Google Sheets integration for production tracking.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from google.oauth2 import service_account
import gspread

from reel_factory.models import SheetsRow


class SheetsClient:
    """Client for Google Sheets operations."""

    def __init__(self, service_account_file: Optional[str] = None):
        self.service_account_file = service_account_file or os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
        self._client = None

    def _get_client(self):
        if self._client is None:
            creds = service_account.Credentials.from_service_account_file(
                self.service_account_file,
                scopes=["https://www.googleapis.com/auth/spreadsheets"],
            )
            self._client = gspread.authorize(creds)
        return self._client

    def append_row(self, spreadsheet_id: str, row: SheetsRow) -> None:
        """Append a production log row to the spreadsheet."""
        client = self._get_client()
        sheet = client.open_by_key(spreadsheet_id).sheet1
        values = [
            row.job_id, row.run_date, row.status, row.language,
            row.source_family or "", row.source_id or "", row.quote_mode or "",
            row.script_score or "", row.storyboard_score or "",
            row.image_score or "", row.shot_score or "", row.final_score or "",
            row.source_attempts, row.script_attempts, row.image_attempts,
            row.shot_attempts, row.final_attempts,
            str(row.used_best_so_far_fallback), row.fallback_stage_list,
            row.drive_folder_url or "", row.final_video_path or "",
            row.publishing_status, row.actual_cost, row.last_error or "",
        ]
        sheet.append_row(values, value_input_option="USER_ENTERED")

    def update_row(self, spreadsheet_id: str, job_id: str, row: SheetsRow) -> None:
        """Update an existing row by job_id."""
        client = self._get_client()
        sheet = client.open_by_key(spreadsheet_id).sheet1
        records = sheet.get_all_records()
        for i, record in enumerate(records):
            if record.get("job_id") == job_id:
                # Row index is 1-based + header row
                row_num = i + 2
                values = [
                    row.job_id, row.run_date, row.status, row.language,
                    row.source_family or "", row.source_id or "", row.quote_mode or "",
                    row.script_score or "", row.storyboard_score or "",
                    row.image_score or "", row.shot_score or "", row.final_score or "",
                    row.source_attempts, row.script_attempts, row.image_attempts,
                    row.shot_attempts, row.final_attempts,
                    str(row.used_best_so_far_fallback), row.fallback_stage_list,
                    row.drive_folder_url or "", row.final_video_path or "",
                    row.publishing_status, row.actual_cost, row.last_error or "",
                ]
                sheet.update(f"A{row_num}:X{row_num}", [values])
                return
        # If not found, append
        self.append_row(spreadsheet_id, row)
