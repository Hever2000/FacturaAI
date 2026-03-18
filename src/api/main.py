from fastapi import FastAPI, UploadFile, File, HTTPException
from uuid import uuid4
import os
import tempfile
import logging
from typing import Dict, Any

from src.core.ocr import process_ocr, extract_invoice_fields

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("zenith_ocr")

app = FastAPI(
    title="ZenithOCR API",
    description="OCR + LLM invoice processing API for Argentine invoices",
    version="1.0.0",
)

jobs_db: Dict[str, Any] = {}


@app.post("/v1/process", status_code=202, summary="Process invoice image")
async def create_process_job(file: UploadFile = File(...)):
    """
    Upload an invoice image and process it with OCR + LLM.

    - **file**: Invoice image (PNG, JPG, PDF)
    - Returns job_id for status checking
    """
    logger.info(f"Received file upload: {file.filename}")

    job_id = str(uuid4())
    suffix = os.path.splitext(file.filename or ".png")[1] or ".png"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        logger.info(f"Processing job {job_id}: OCR step")
        ocr_result = process_ocr(tmp_path)

        jobs_db[job_id] = {
            "id": job_id,
            "status": "PROCESSING_LLM",
            "filename": file.filename,
            "raw_text": ocr_result["raw_text"],
            "full_text": ocr_result["full_text"],
        }

        logger.info(f"Processing job {job_id}: LLM extraction step")
        llm_result = extract_invoice_fields(ocr_result["full_text"])

        jobs_db[job_id]["status"] = "PROCESSED"
        jobs_db[job_id]["extracted_data"] = llm_result

        logger.info(f"Job {job_id} completed successfully")

    except Exception as e:
        logger.error(f"Job {job_id} failed: {str(e)}")
        jobs_db[job_id] = {
            "id": job_id,
            "status": "FAILED",
            "filename": file.filename,
            "error": str(e),
        }
    finally:
        os.unlink(tmp_path)

    return {"job_id": job_id, "status": jobs_db[job_id]["status"]}


@app.get("/v1/jobs/{job_id}", summary="Get job status")
async def get_job_status(job_id: str):
    """
    Get the status and results of a processing job.

    - **job_id**: Job ID returned from /v1/process
    """
    job = jobs_db.get(job_id)
    if not job:
        logger.warning(f"Job not found: {job_id}")
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/v1/jobs/{job_id}/export", summary="Export job as JSON")
async def export_job_json(job_id: str):
    """
    Export processed invoice data as JSON file.

    - **job_id**: Job ID with processed data
    """
    job = jobs_db.get(job_id)
    if not job:
        logger.warning(f"Job not found for export: {job_id}")
        raise HTTPException(status_code=404, detail="Job not found")

    if job.get("status") != "PROCESSED":
        logger.warning(f"Job not processed: {job_id}")
        raise HTTPException(status_code=400, detail="Job not yet processed")

    from fastapi.responses import Response
    import json

    export_data = {
        "job_id": job["id"],
        "filename": job["filename"],
        "invoice_data": job.get("extracted_data", {}),
        "raw_text": job.get("full_text", ""),
    }

    logger.info(f"Exporting job {job_id} as JSON")

    return Response(
        content=json.dumps(export_data, indent=2, ensure_ascii=False),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=invoice_{job_id}.json"},
    )


@app.get("/health", summary="Health check")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "zenith-ocr"}
