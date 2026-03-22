import json
import logging
import os
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select

from src.api.deps import CurrentUser, DBSession
from src.core.config import settings
from src.core.feedback import (
    add_correction as add_feedback_correction,
)
from src.core.feedback import (
    export_training_jsonl as do_export,
)
from src.core.feedback import (
    get_feedback_stats as do_stats,
)
from src.core.ocr import extract_invoice_fields, process_ocr
from src.models.feedback import Feedback
from src.models.job import Job

logger = logging.getLogger("facturaai")

router = APIRouter(prefix="/jobs", tags=["Jobs"])


def format_invoice_as_text(data: dict[str, Any]) -> str:
    """Format extracted invoice data as plain text."""
    lines = []
    lines.append("=" * 60)
    lines.append("FACTURA PROCESADA - FacturaAI")
    lines.append("=" * 60)
    lines.append("")

    def safe_val(value: Any) -> str:
        if value is None or value == "":
            return "No disponible"
        if isinstance(value, (int, float)):
            return f"${value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return str(value)

    def safe_str(value: Any) -> str:
        if value is None or value == "":
            return "No disponible"
        return str(value)

    lines.append("COMPROBANTE")
    lines.append("-" * 40)
    lines.append(f"Tipo: {safe_str(data.get('tipo_comprobante'))}")
    lines.append(f"Letra: {safe_str(data.get('letra_comprobante'))}")
    lines.append(f"Punto de Venta: {safe_str(data.get('punto_de_venta'))}")
    lines.append(f"Número: {safe_str(data.get('numero_comprobante'))}")
    lines.append(f"Fecha de Emisión: {safe_str(data.get('fecha_emision'))}")
    lines.append(f"Fecha Vencimiento: {safe_str(data.get('fecha_vencimiento_pago'))}")
    if data.get("cae"):
        lines.append(f"CAE: {safe_str(data.get('cae'))}")
        lines.append(f"Vencimiento CAE: {safe_str(data.get('fecha_vencimiento_cae'))}")
    lines.append("")

    lines.append("VENDEDOR")
    lines.append("-" * 40)
    lines.append(f"Razón Social: {safe_str(data.get('razon_social_vendedor'))}")
    lines.append(f"CUIT: {safe_str(data.get('vendedor_cuit'))}")
    lines.append(f"Condición IVA: {safe_str(data.get('vendedor_condicion_iva'))}")
    if data.get("vendedor_ingresos_brutos"):
        lines.append(f"Ingresos Brutos: {safe_str(data.get('vendedor_ingresos_brutos'))}")
    lines.append(f"Domicilio: {safe_str(data.get('vendedor_domicilio'))}")
    lines.append(f"Localidad: {safe_str(data.get('vendedor_localidad'))}")
    lines.append("")

    lines.append("CLIENTE")
    lines.append("-" * 40)
    lines.append(f"Razón Social: {safe_str(data.get('razon_social_cliente'))}")
    lines.append(f"CUIT: {safe_str(data.get('cliente_cuit'))}")
    lines.append(f"Condición IVA: {safe_str(data.get('cliente_condicion_iva'))}")
    lines.append(f"Domicilio: {safe_str(data.get('cliente_domicilio'))}")
    lines.append(f"Localidad: {safe_str(data.get('cliente_localidad'))}")
    lines.append("")

    items = data.get("items", [])
    if items:
        lines.append("DETALLE DE ITEMS")
        lines.append("-" * 40)
        lines.append(
            f"{'#':<4} {'Descripción':<30} {'Cant.':<8} {'Precio Unit.':<15} {'Total':<15}"
        )
        lines.append("-" * 72)
        for i, item in enumerate(items, 1):
            desc = safe_str(item.get("descripcion", ""))[:28]
            cant = item.get("cantidad", 1)
            precio = safe_val(item.get("precio_unitario", 0))
            total = safe_val(item.get("total_item", 0))
            lines.append(f"{i:<4} {desc:<30} {cant:<8.2f} {precio:<15} {total:<15}")
        lines.append("")

    lines.append("TOTALES")
    lines.append("-" * 40)
    lines.append(f"Subtotal:          {safe_val(data.get('subtotal', 0))}")
    lines.append(f"Neto Gravado:      {safe_val(data.get('importe_neto_gravado', 0))}")
    lines.append(f"Neto No Gravado:    {safe_val(data.get('importe_neto_no_gravado', 0))}")
    lines.append(f"Exento:            {safe_val(data.get('importe_exento', 0))}")
    lines.append("")
    lines.append("IMPUESTOS (IVA)")
    lines.append("-" * 40)
    ivas = [
        ("IVA 27%", data.get("iva_27", 0)),
        ("IVA 21%", data.get("iva_21", 0)),
        ("IVA 10.5%", data.get("iva_10_5", 0)),
        ("IVA 5%", data.get("iva_5", 0)),
        ("IVA 2.5%", data.get("iva_2_5", 0)),
        ("IVA 0%", data.get("iva_0", 0)),
    ]
    for label, value in ivas:
        if value and value > 0:
            lines.append(f"{label:<15} {safe_val(value)}")
    lines.append(f"{'Total IVA:':<15} {safe_val(data.get('total_iva', 0))}")
    lines.append("")
    if data.get("importe_otros_tributos"):
        lines.append(f"Otros Tributos:    {safe_val(data.get('importe_otros_tributos', 0))}")
        lines.append(f"Total Tributos:    {safe_val(data.get('total_tributos', 0))}")
        lines.append("")
    lines.append(f"{'TOTAL:':<40} {safe_val(data.get('total', 0))}")
    lines.append("")
    lines.append(f"Condición de Pago: {safe_str(data.get('condicion_pago'))}")

    if data.get("observaciones"):
        lines.append("")
        lines.append("OBSERVACIONES")
        lines.append("-" * 40)
        lines.append(safe_str(data.get("observaciones")))

    lines.append("")
    lines.append("=" * 60)
    lines.append("Procesado por FacturaAI - OCR + IA")
    lines.append("=" * 60)

    return "\n".join(lines)


class FeedbackRequest(BaseModel):
    """Request model for feedback submission."""

    field: str
    correct_value: Any


class JobListResponse(BaseModel):
    """Paginated job list."""

    jobs: list[dict]
    total: int
    page: int
    page_size: int


@router.post("/process", status_code=status.HTTP_202_ACCEPTED)
async def process_invoice(
    db: DBSession,
    current_user: CurrentUser,
    file: UploadFile = File(...),  # noqa: B008
) -> dict:
    """
    Upload an invoice image and process it with OCR + LLM.

    - **file**: Invoice image (PNG, JPG, PDF)
    - Requires authentication
    - Subject to rate limiting and monthly quota
    - Returns job_id for status checking
    """
    from src.api.deps import check_monthly_quota, check_rate_limit
    from src.services.auth import AuthService

    # Check rate limit (per-minute)
    await check_rate_limit(current_user)

    # Check monthly quota
    await check_monthly_quota(current_user)

    # Validate file type
    allowed_types = {"image/png", "image/jpeg", "image/jpg", "application/pdf"}
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file.content_type}. Allowed: PNG, JPG, PDF",
        )

    # Check file size
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > settings.MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large: {size_mb:.1f}MB. Max: {settings.MAX_FILE_SIZE_MB}MB",
        )

    # Save file to storage
    suffix = os.path.splitext(file.filename or ".png")[1] or ".png"
    filename = f"{uuid4()}{suffix}"
    file_path = os.path.join(settings.STORAGE_PATH, filename)

    with open(file_path, "wb") as f:
        f.write(content)

    # Create job record
    job = Job(
        user_id=current_user.id,
        status="processing",
        filename=file.filename,
        file_path=file_path,
        file_size=len(content),
        content_type=file.content_type,
    )
    db.add(job)
    await db.flush()
    await db.refresh(job)

    job_id = str(job.id)

    try:
        # OCR step
        logger.info(f"Job {job_id}: Starting OCR")
        ocr_result = process_ocr(file_path)

        if "error" in ocr_result or ocr_result.get("status") == "OCR_FAILED":
            error_msg = ocr_result.get("error", "Unknown OCR error")
            logger.error(f"Job {job_id} OCR failed: {error_msg}")
            job.status = "failed"
            job.error_message = error_msg
            await db.flush()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"OCR processing failed: {error_msg}",
            )

        job.ocr_engine = ocr_result.get("ocr_engine", "unknown")
        job.raw_text = json.dumps(ocr_result.get("raw_text", []))
        await db.flush()

        # LLM extraction step
        logger.info(f"Job {job_id}: Starting LLM extraction")
        extracted_data = extract_invoice_fields(ocr_result["full_text"])

        if "error" in extracted_data:
            error_msg = extracted_data.get("error", "Unknown LLM error")
            logger.error(f"Job {job_id} LLM failed: {error_msg}")
            job.status = "failed"
            job.error_message = error_msg
            await db.flush()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"LLM extraction failed: {error_msg}",
            )

        job.extracted_data = extracted_data
        job.status = "completed"
        await db.flush()

        # Increment user's monthly request count
        auth_service = AuthService(db)
        has_quota, _, _ = await auth_service.check_usage_and_increment(current_user, reset_if_needed=True)

        logger.info(f"Job {job_id} completed successfully")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Job {job_id} failed: {str(e)}")
        job.status = "failed"
        job.error_message = str(e)
        job.retry_count = job.retry_count + 1
        await db.flush()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Processing failed: {str(e)}",
        )
    finally:
        # Remove temp file from storage (already saved in job)
        if os.path.exists(file_path):
            pass  # Keep file for reference

    return {"job_id": job_id, "status": job.status}


@router.get("", response_model=JobListResponse)
async def list_jobs(
    db: DBSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: str | None = Query(None),
) -> JobListResponse:
    """List all jobs for the current user with pagination."""
    query = select(Job).where(Job.user_id == current_user.id)

    if status_filter:
        query = query.where(Job.status == status_filter)

    query = query.order_by(Job.created_at.desc())

    # Count total
    from sqlalchemy import func

    count_query = select(func.count()).select_from(Job).where(Job.user_id == current_user.id)
    if status_filter:
        count_query = count_query.where(Job.status == status_filter)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    jobs = result.scalars().all()

    return JobListResponse(
        jobs=[
            {
                "id": str(j.id),
                "status": j.status,
                "filename": j.filename,
                "content_type": j.content_type,
                "ocr_engine": j.ocr_engine,
                "has_results": j.extracted_data is not None,
                "created_at": j.created_at.isoformat() if j.created_at else None,
                "updated_at": j.updated_at.isoformat() if j.updated_at else None,
            }
            for j in jobs
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{job_id}")
async def get_job(
    job_id: UUID,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    """Get job status and results."""
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == current_user.id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "id": str(job.id),
        "status": job.status,
        "filename": job.filename,
        "content_type": job.content_type,
        "ocr_engine": job.ocr_engine,
        "raw_text": json.loads(job.raw_text) if job.raw_text else None,
        "extracted_data": job.extracted_data,
        "extraction_confidence": job.extraction_confidence,
        "error_message": job.error_message,
        "retry_count": job.retry_count,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


@router.get("/{job_id}/export")
async def export_job(
    job_id: UUID,
    db: DBSession,
    current_user: CurrentUser,
    format: str = Query("json", pattern="^(json|txt)$"),
) -> Response:  # noqa: B008
    """Export processed invoice data as JSON or plain text."""
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == current_user.id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != "completed":
        raise HTTPException(status_code=400, detail="Job not yet processed")

    if format == "txt":
        text_content = format_invoice_as_text(job.extracted_data or {})
        return Response(
            content=text_content,
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename=invoice_{job_id}.txt"},
        )

    export_data = {
        "job_id": str(job.id),
        "filename": job.filename,
        "ocr_engine": job.ocr_engine,
        "invoice_data": job.extracted_data,
        "raw_text": json.loads(job.raw_text) if job.raw_text else None,
    }

    return Response(
        content=json.dumps(export_data, indent=2, ensure_ascii=False),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=invoice_{job_id}.json"},
    )


@router.get("/{job_id}/text")
async def get_job_text(
    job_id: UUID,
    db: DBSession,
    current_user: CurrentUser,
) -> Response:  # noqa: B008
    """Get the processed invoice data as formatted plain text."""
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == current_user.id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != "completed":
        raise HTTPException(status_code=400, detail="Job not yet processed")

    text_content = format_invoice_as_text(job.extracted_data or {})

    return Response(
        content=text_content,
        media_type="text/plain; charset=utf-8",
    )


@router.post("/{job_id}/feedback")
async def submit_feedback(
    job_id: UUID,
    feedback: FeedbackRequest,
    db: DBSession,
    current_user: CurrentUser,
) -> dict:
    """Submit a correction for a processed invoice field."""
    result = await db.execute(
        select(Job).where(Job.id == job_id, Job.user_id == current_user.id)
    )
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != "completed":
        raise HTTPException(status_code=400, detail="Job not yet processed")

    # Handle nested item fields (e.g., "items[0].descripcion")
    wrong_value = None
    extracted_data = job.extracted_data or {}

    if "." in feedback.field:
        parts = feedback.field.split(".")
        if parts[0] == "items" and len(parts) == 3:
            idx = int(parts[1])
            field_name = parts[2]
            items = extracted_data.get("items", [])
            if idx < len(items):
                wrong_value = items[idx].get(field_name)
    else:
        wrong_value = extracted_data.get(feedback.field)

    # Save to DB
    fb = Feedback(
        user_id=current_user.id,
        job_id=job.id,
        field_name=feedback.field,
        original_value={"value": wrong_value} if wrong_value is not None else None,
        corrected_value={"value": feedback.correct_value},
        raw_text_snippet=job.raw_text[:500] if job.raw_text else None,
        ai_response_snapshot=extracted_data,
    )
    db.add(fb)
    await db.flush()
    await db.refresh(fb)

    # Also save to feedback system for LLM few-shot learning
    add_feedback_correction(
        job_id=str(job.id),
        field=feedback.field,
        wrong_value=wrong_value,
        correct_value=feedback.correct_value,
        raw_text=job.raw_text or "",
        extracted_data=extracted_data,
    )

    logger.info(f"Feedback submitted for job {job_id}: {feedback.field}")

    return {
        "status": "saved",
        "feedback_id": str(fb.id),
        "feedback_count": do_stats()["total_corrections"],
    }


@router.get("/training-data/export")
async def export_training_data() -> Response:
    """
    Export feedback corrections as JSONL for model fine-tuning.
    Public endpoint (used by ML pipeline).
    """
    filepath = do_export()

    with open(filepath, encoding="utf-8") as f:
        content = f.read()

    logger.info(f"Training data exported: {filepath}")

    return Response(
        content=content,
        media_type="application/jsonl",
        headers={"Content-Disposition": "attachment; filename=training_data.jsonl"},
    )


@router.get("/feedback/stats")
async def feedback_stats() -> dict:
    """Get statistics about submitted feedback corrections."""
    return do_stats()
