"""
Shared utilities for downloading files from fal.ai URLs.

Handles SSL certificate issues on macOS where the system certificate
store may not include all required CAs (common with VPN/proxy setups).
"""
from __future__ import annotations

import ssl
import urllib.request
from pathlib import Path
from typing import Optional


def _get_ssl_context() -> ssl.SSLContext:
    """Get an SSL context with certifi certificates for reliable downloads."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        # Fallback to system default if certifi not installed
        return ssl.create_default_context()


def download_file(url: str, dest_path: str) -> bool:
    """Download a file from a URL to a local path.
    
    Uses certifi for SSL certificates to avoid macOS certificate issues.
    Returns True on success, False on failure.
    """
    try:
        ctx = _get_ssl_context()
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, context=ctx) as resp:
            Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
            with open(dest_path, "wb") as f:
                f.write(resp.read())
        return True
    except Exception:
        return False