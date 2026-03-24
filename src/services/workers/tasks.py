import logging
from typing import Any

from celery import Task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.core.config import settings

logger = logging.getLogger("facturaai")

engine = create_async_engine(settings.DATABASE_URL, echo=False)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False)


class AsyncJobTask(Task):
    """Base class for async job tasks with database session management."""

    _db: AsyncSession | None = None

    @property
    def db(self) -> AsyncSession:
        if self._db is None:
            raise RuntimeError("Database session not initialized")
        return self._db

    def before_start(self, task_id: str, args: tuple, kwargs: dict) -> None:
        """Initialize database session before task starts."""
        import asyncio
        loop = asyncio.get_event_loop()
        self._db = loop.run_until_complete(async_session_maker().__aenter__())

    def after_return(self, status: str, retval: Any, task_id: str, args: tuple, kwargs: dict) -> None:
        """Close database session after task completes."""
        if self._db is not None:
            import asyncio
            loop = asyncio.get_event_loop()
            loop.run_until_complete(self._db.close())


def update_job_status(
    job_id: str,
    status: str,
    error_message: str | None = None,
    extracted_data: dict | None = None,
    raw_text: str | None = None,
    ocr_engine: str | None = None,
    extraction_confidence: float | None = None,
) -> None:
    """Update job status in database."""
    import asyncio

    async def _update():
        async with async_session_maker() as session:
            from src.models.job import Job

            result = await session.execute(
                select(Job).where(Job.id == job_id)
            )
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

    asyncio.run(_update())


def increment_user_usage(user_id: str) -> None:
    """Increment user's monthly request count."""
    import asyncio

    async def _increment():
        async with async_session_maker() as session:

            from src.models.user import User

            result = await session.execute(
                select(User).where(User.id == user_id)
            )
            user = result.scalar_one_or_none()

            if user:
                user.monthly_request_count += 1
                await session.commit()
                logger.info(f"User {user_id} usage incremented")

    asyncio.run(_increment())


def process_job_task(
    job_id: str,
    user_id: str,
    file_path: str,
) -> dict[str, Any]:
    """Process a job: OCR + LLM extraction."""
    logger.info(f"Starting job processing: job_id={job_id}")

    try:
        update_job_status(job_id, "processing")

        from src.services.llm_service import LLMService
        from src.services.ocr_service import OCRService

        ocr_service = OCRService()
        llm_service = LLMService()

        logger.info(f"Job {job_id}: Starting OCR")
        ocr_result = ocr_service.process(file_path)

        if "error" in ocr_result or ocr_result.get("status") == "OCR_FAILED":
            error_msg = ocr_result.get("error", "Unknown OCR error")
            logger.error(f"Job {job_id} OCR failed: {error_msg}")
            update_job_status(job_id, "failed", error_message=error_msg)
            return {"status": "failed", "error": error_msg}

        update_job_status(
            job_id,
            "processing",
            raw_text=ocr_result.get("raw_text"),
            ocr_engine=ocr_result.get("ocr_engine"),
        )

        logger.info(f"Job {job_id}: Starting LLM extraction")
        extracted_data = llm_service.extract_invoice_fields(ocr_result["full_text"])

        if "error" in extracted_data:
            error_msg = extracted_data.get("error", "Unknown LLM error")
            logger.error(f"Job {job_id} LLM failed: {error_msg}")
            update_job_status(job_id, "failed", error_message=error_msg)
            return {"status": "failed", "error": error_msg}

        confidence = extracted_data.get("confidence_score", 0.8)
        update_job_status(
            job_id,
            "completed",
            extracted_data=extracted_data,
            extraction_confidence=confidence,
        )

        increment_user_usage(user_id)

        logger.info(f"Job {job_id} completed successfully")
        return {"status": "completed", "job_id": job_id}

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Job {job_id} failed with exception: {error_msg}")
        update_job_status(job_id, "failed", error_message=error_msg)
        return {"status": "failed", "error": error_msg}


def retry_job_task(job_id: str, max_retries: int = 3) -> dict[str, Any]:
    """Retry a failed job."""
    import asyncio

    async def _retry():
        async with async_session_maker() as session:
            from src.models.job import Job

            result = await session.execute(
                select(Job).where(Job.id == job_id)
            )
            job = result.scalar_one_or_none()

            if not job:
                return {"status": "error", "message": "Job not found"}

            if job.retry_count >= max_retries:
                logger.warning(f"Job {job_id} exceeded max retries")
                return {"status": "error", "message": "Max retries exceeded"}

            job.retry_count += 1
            await session.commit()

            process_job_task(
                job_id=str(job.id),
                user_id=str(job.user_id),
                file_path=job.file_path,
            )

            return {"status": "retry_scheduled", "job_id": job_id}

    return asyncio.run(_retry())
