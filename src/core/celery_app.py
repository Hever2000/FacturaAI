import os

from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "factura_ai",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "src.services.workers.tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "src.services.workers.tasks.process_job_task": {"queue": "ocr_jobs"},
        "src.services.workers.tasks.retry_job_task": {"queue": "ocr_jobs"},
    },
    task_default_queue="ocr_jobs",
    task_default_exchange="ocr_jobs",
    task_default_routing_key="ocr_jobs",
)
