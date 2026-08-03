"""
Google Drive integration for asset archival.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from reel_factory.models import DriveManifest, JobRecord


class DriveClient:
    """Client for Google Drive operations."""

    def __init__(self, service_account_file: Optional[str] = None):
        self.service_account_file = service_account_file or os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
        self._service = None

    def _get_service(self):
        if self._service is None:
            if not self.service_account_file:
                raise RuntimeError(
                    "Google Drive not configured: GOOGLE_SERVICE_ACCOUNT_FILE not set"
                )
            creds = service_account.Credentials.from_service_account_file(
                self.service_account_file,
                scopes=["https://www.googleapis.com/auth/drive.file"],
            )
            self._service = build("drive", "v3", credentials=creds)
        return self._service

    def is_configured(self) -> bool:
        """Check if Drive is properly configured."""
        return bool(self.service_account_file)

    def create_folder(self, name: str, parent_id: Optional[str] = None) -> str:
        """Create a folder in Google Drive and return its ID."""
        service = self._get_service()
        file_metadata = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_id:
            file_metadata["parents"] = [parent_id]

        folder = service.files().create(body=file_metadata, fields="id").execute()
        return folder.get("id")

    def upload_file(
        self,
        file_path: str | Path,
        folder_id: str,
        mime_type: str = "application/octet-stream",
    ) -> str:
        """Upload a file to a Drive folder and return its web view link."""
        service = self._get_service()
        media = MediaFileUpload(str(file_path), mimetype=mime_type, resumable=True)
        file_metadata = {
            "name": Path(file_path).name,
            "parents": [folder_id],
        }
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id,webViewLink",
        ).execute()
        return file.get("webViewLink", "")

    def upload_manifest(self, manifest: DriveManifest, folder_id: str) -> str:
        """Upload a manifest JSON file to the job folder."""
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(manifest.model_dump(mode="json"), f, indent=2)
            temp_path = f.name
        try:
            return self.upload_file(temp_path, folder_id, "application/json")
        finally:
            Path(temp_path).unlink(missing_ok=True)
