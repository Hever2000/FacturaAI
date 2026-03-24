"""
Async job processor for invoice OCR + LLM extraction.

This module provides a simple async-based job processor that runs
in the same process as the API, using FastAPI's BackgroundTasks.

For production with high load, consider:
- Separate worker service with Redis queue (Celery)
- Upstash QStash for serverless queue

Usage:
    from src.services.workers.async_processor import process_job_background

    # In your endpoint:
    background_tasks.add_task(
        process_job_background,
        job_id=str(job.id),
        user_id=str(current_user.id),
        file_key=file_key,
    )
"""

import logging
from typing import Any

from sqlalchemy import select

from src.db.session import async_session_maker

logger = logging.getLogger("facturaai")


async def update_job_status(
    job_id: str,
    status: str,
    error_message: str | None = None,
    extracted_data: dict | None = None,
    raw_text: str | None = None,
    ocr_engine: str | None = None,
    extraction_confidence: float | None = None,
) -> None:
    """Update job status in database."""
    async with async_session_maker() as session:
        from src.models.job import Job

        result = await session.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()

        if job:
            job.status = status
            if error_message:
                job.error_message = error_message
            if extracted_data is not None:
                job.extracted_data = extracted_data
            if raw_text is not None:
                job.raw_text = raw_text
            if ocr_engine is not None:
                job.ocr_engine = ocr_engine
            if extraction_confidence is not None:
                job.extraction_confidence = extraction_confidence

            await session.commit()
            logger.info(f"Job {job_id} status updated to: {status}")


async def increment_user_usage(user_id: str) -> None:
    """Increment user's monthly request count."""
    async with async_session_maker() as session:
        from src.models.user import User

        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if user:
            user.monthly_request_count += 1
            await session.commit()
            logger.info(f"User {user_id} usage incremented")


async def process_job_background(
    job_id: str,
    user_id: str,
    file_key: str,
) -> dict[str, Any]:
    """
    Process a job in the background: OCR + LLM extraction.

    This runs as an async task within the API process.
    For high-volume production, use a separate worker service.

    Args:
        job_id: The job UUID
        user_id: The user UUID who owns the job
        file_key: The storage key for the uploaded file

    Returns:
        Dict with status and any error info
    """
    logger.info(f"Starting background job processing: job_id={job_id}")

    try:
        # Update status to processing
        await update_job_status(job_id, "processing")

        # Get file content from storage
        from src.services.storage import storage_service

        file_content = await storage_service.get_file_content(file_key)
        if not file_content:
            error_msg = "File not found in storage"
            logger.error(f"Job {job_id}: {error_msg}")
            await update_job_status(job_id, "failed", error_message=error_msg)
            return {"status": "failed", "error": error_msg}

        # Save to temp file for OCR processing
        import os
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name

        try:
            # Process OCR
            from src.services.llm_service import LLMService
            from src.services.ocr_service import OCRService

            ocr_service = OCRService()
            llm_service = LLMService()

            logger.info(f"Job {job_id}: Starting OCR")
            ocr_result = ocr_service.process(tmp_path)

            if "error" in ocr_result or ocr_result.get("status") == "OCR_FAILED":
                error_msg = ocr_result.get("error", "Unknown OCR error")
                logger.error(f"Job {job_id} OCR failed: {error_msg}")
                await update_job_status(job_id, "failed", error_message=error_msg)
                return {"status": "failed", "error": error_msg}

            await update_job_status(
                job_id,
                "processing",
                raw_text=ocr_result.get("raw_text"),
                ocr_engine=ocr_result.get("ocr_engine"),
            )

            # LLM extraction
            logger.info(f"Job {job_id}: Starting LLM extraction")
            extracted_data = llm_service.extract_invoice_fields(ocr_result["full_text"])

            if "error" in extracted_data:
                error_msg = extracted_data.get("error", "Unknown LLM error")
                logger.error(f"Job {job_id} LLM failed: {error_msg}")
                await update_job_status(job_id, "failed", error_message=error_msg)
                return {"status": "failed", "error": error_msg}

            confidence = extracted_data.get("confidence_score", 0.8)
            await update_job_status(
                job_id,
                "completed",
                extracted_data=extracted_data,
                extraction_confidence=confidence,
            )

            # Increment user usage
            await increment_user_usage(user_id)

            logger.info(f"Job {job_id} completed successfully")
            return {"status": "completed", "job_id": job_id}

        finally:
            # Cleanup temp file
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Job {job_id} failed with exception: {error_msg}")
        await update_job_status(job_id, "failed", error_message=error_msg)
        return {"status": "failed", "error": error_msg}


async def retry_job_background(
    job_id: str,
    max_retries: int = 3,
) -> dict[str, Any]:
    """Retry a failed job in the background."""
    async with async_session_maker() as session:
        from src.models.job import Job

        result = await session.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()

        if not job:
            return {"status": "error", "message": "Job not found"}

        if job.retry_count >= max_retries:
            logger.warning(f"Job {job_id} exceeded max retries")
            return {"status": "error", "message": "Max retries exceeded"}

        job.retry_count += 1
        await session.commit()

        # Process in background
        return await process_job_background(
            job_id=str(job.id),
            user_id=str(job.user_id),
            file_key=job.file_path,
        )
