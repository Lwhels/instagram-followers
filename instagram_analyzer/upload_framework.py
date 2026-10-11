"""Production-grade file upload framework for Instagram export archives.
Includes safe storage, archive traversal protection (Zip-Slip prevention),
zip-bomb limits, asynchronous job tracking, and progress reporting.
"""

import asyncio
import os
import shutil
import uuid
import zipfile
from datetime import datetime
from typing import Dict, Optional, Tuple
from fastapi import UploadFile

from instagram_analyzer.models import UploadJobResponse, UploadJobStatus
from instagram_analyzer.parser import (
    ParsedEntry,
    parse_file,
    parse_html_content,
    parse_json_content,
    parse_zip_archive,
)

MAX_UPLOAD_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB
MAX_DECOMPRESSED_RATIO = 100               # Zip-bomb protection: 100x max compression ratio


class UploadSecurityError(Exception):
    """Raised when file validation or archive safety check fails."""
    pass


class UploadStorage:
    def __init__(self, base_dir: str = "uploads_staging"):
        self.base_dir = base_dir
        os.makedirs(self.base_dir, exist_ok=True)

    def save_upload_stream(self, file_obj, original_filename: str) -> Tuple[str, str]:
        """Save file to staging area with a unique secure filename."""
        ext = os.path.splitext(original_filename)[1].lower()
        if ext not in {".zip", ".html", ".htm", ".json"}:
            raise UploadSecurityError(f"Unsupported file format: {ext}. Expected .zip, .html, or .json")

        file_id = str(uuid.uuid4())
        safe_path = os.path.join(self.base_dir, f"{file_id}{ext}")

        size = 0
        with open(safe_path, "wb") as dest:
            while chunk := file_obj.read(1024 * 1024):  # 1MB chunks
                size += len(chunk)
                if size > MAX_UPLOAD_SIZE_BYTES:
                    os.remove(safe_path)
                    raise UploadSecurityError(f"File size exceeds maximum limit of {MAX_UPLOAD_SIZE_BYTES // (1024*1024)}MB")
                dest.write(chunk)

        # Zip bomb / Zip Slip validation
        if ext == ".zip":
            self._validate_zip_archive(safe_path, size)

        return file_id, safe_path

    def _validate_zip_archive(self, zip_path: str, compressed_size: int):
        """Validate zip integrity and guard against Zip Slip and Zip Bombs."""
        with zipfile.ZipFile(zip_path, "r") as z:
            total_uncompressed = 0
            for info in z.infolist():
                # Zip Slip path traversal check
                filename = info.filename
                if os.path.isabs(filename) or ".." in filename.split("/"):
                    raise UploadSecurityError(f"Malicious archive member detected: {filename}")

                total_uncompressed += info.file_size
                if total_uncompressed > compressed_size * MAX_DECOMPRESSED_RATIO:
                    raise UploadSecurityError("Archive decompression ratio exceeded safety limits (potential zip bomb)")

    def cleanup(self, file_path: str):
        """Remove staged file after processing."""
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass


async def process_upload_task(
    job_id: str,
    user_id: int,
    file_path: str,
    snapshot_name: str,
    db,
    storage: UploadStorage,
):
    """
    Background worker task to process uploaded file,
    update job progress stages, and insert snapshot into database.
    """
    try:
        db.update_upload_job(job_id, status=UploadJobStatus.PROCESSING, stage="extracting", progress=10.0)
        ext = os.path.splitext(file_path)[1].lower()

        followers = []
        following = []

        if ext == ".zip":
            db.update_upload_job(job_id, stage="parsing_zip_archive", progress=30.0)
            followers, following = parse_zip_archive(file_path)
        elif "follower" in os.path.basename(file_path).lower():
            db.update_upload_job(job_id, stage="parsing_followers", progress=40.0)
            followers = parse_file(file_path)
        else:
            db.update_upload_job(job_id, stage="parsing_following", progress=40.0)
            following = parse_file(file_path)

        total_items = len(followers) + len(following)
        db.update_upload_job(
            job_id,
            stage="indexing_database",
            progress=75.0,
            total_items=total_items,
            processed_items=total_items,
        )

        # Save snapshot scoped to user_id
        snap_id = db.save_snapshot(
            name=snapshot_name,
            followers=followers,
            following=following,
            user_id=user_id,
        )

        db.complete_upload_job(job_id, snapshot_id=snap_id)

    except Exception as e:
        db.fail_upload_job(job_id, error_message=str(e))
    finally:
        storage.cleanup(file_path)
