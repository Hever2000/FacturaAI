import logging
import os
import tempfile
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from src.core.feedback import (
    add_correction,
    export_training_jsonl,
    get_feedback_stats,
)
from src.core.ocr import extract_invoice_fields, process_ocr

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("factura_ai")


class FeedbackRequest(BaseModel):
    """Request model for feedback submission."""

    field: str = Field(..., description="Field name that was incorrectly extracted")
    correct_value: Any = Field(..., description="The correct value for this field")


app = FastAPI(
    title="FacturaAI API",
    description="OCR + LLM invoice processing API for Argentine invoices",
    version="1.0.0",
)

jobs_db: dict[str, Any] = {}


def format_invoice_as_text(data: dict[str, Any]) -> str:
    """
    Formatea los datos de la factura como texto plano legible.

    Args:
        data: Diccionario con los datos extraídos de la factura

    Returns:
        String con formato de texto plano
    """
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


@app.post("/v1/process", status_code=202, summary="Process invoice image")
async def create_process_job(file: UploadFile = File(...)):  # noqa: B008
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

        if "error" in ocr_result or ocr_result.get("status") == "OCR_FAILED":
            error_msg = ocr_result.get("error", "Unknown OCR error")
            logger.error(f"OCR failed for job {job_id}: {error_msg}")
            raise Exception(f"OCR processing failed: {error_msg}")

        jobs_db[job_id] = {
            "id": job_id,
            "status": "PROCESSING_LLM",
            "filename": file.filename,
            "raw_text": ocr_result["raw_text"],
            "full_text": ocr_result["full_text"],
            "ocr_engine": ocr_result.get("ocr_engine", "unknown"),
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


@app.get("/v1/jobs/{job_id}/export", summary="Export job as JSON or TXT")
async def export_job(job_id: str, format: str = Query("json", regex="^(json|txt)$")):
    """
    Export processed invoice data as JSON or plain text.

    - **job_id**: Job ID with processed data
    - **format**: Export format ('json' or 'txt')
    """
    import json

    job = jobs_db.get(job_id)
    if not job:
        logger.warning(f"Job not found for export: {job_id}")
        raise HTTPException(status_code=404, detail="Job not found")

    if job.get("status") != "PROCESSED":
        logger.warning(f"Job not processed: {job_id}")
        raise HTTPException(status_code=400, detail="Job not yet processed")

    if format == "txt":
        logger.info(f"Exporting job {job_id} as plain text")
        text_content = format_invoice_as_text(job.get("extracted_data", {}))
        return Response(
            content=text_content,
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename=invoice_{job_id}.txt"},
        )

    logger.info(f"Exporting job {job_id} as JSON")
    export_data = {
        "job_id": job["id"],
        "filename": job["filename"],
        "ocr_engine": job.get("ocr_engine", "unknown"),
        "invoice_data": job.get("extracted_data", {}),
        "raw_text": job.get("full_text", ""),
    }

    return Response(
        content=json.dumps(export_data, indent=2, ensure_ascii=False),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=invoice_{job_id}.json"},
    )


@app.get("/v1/jobs/{job_id}/text", summary="Get invoice as plain text")
async def get_job_text(job_id: str):
    """
    Get the processed invoice data as formatted plain text.

    - **job_id**: Job ID with processed data
    """
    job = jobs_db.get(job_id)
    if not job:
        logger.warning(f"Job not found: {job_id}")
        raise HTTPException(status_code=404, detail="Job not found")

    if job.get("status") != "PROCESSED":
        logger.warning(f"Job not processed: {job_id}")
        raise HTTPException(status_code=400, detail="Job not yet processed")

    logger.info(f"Getting job {job_id} as plain text")
    text_content = format_invoice_as_text(job.get("extracted_data", {}))

    return Response(
        content=text_content,
        media_type="text/plain; charset=utf-8",
    )


@app.post("/v1/jobs/{job_id}/feedback", summary="Submit correction feedback")
async def submit_feedback(job_id: str, feedback: FeedbackRequest):
    """
    Submit a correction for a processed invoice field.

    - **job_id**: Job ID with processed data
    - **field**: Field name that was incorrectly extracted
    - **correct_value**: The correct value for this field
    """
    job = jobs_db.get(job_id)
    if not job:
        logger.warning(f"Job not found for feedback: {job_id}")
        raise HTTPException(status_code=404, detail="Job not found")

    if job.get("status") != "PROCESSED":
        logger.warning(f"Job not processed: {job_id}")
        raise HTTPException(status_code=400, detail="Job not yet processed")

    wrong_value = None
    extracted_data = job.get("extracted_data", {})

    # Handle nested item fields (e.g., "items[0].descripcion")
    if "." in feedback.field:
        parts = feedback.field.split(".")
        if parts[0] == "items" and len(parts) == 3:
            idx = int(parts[1])
            field_name = parts[2]
            if idx < len(extracted_data.get("items", [])):
                wrong_value = extracted_data["items"][idx].get(field_name)
    else:
        wrong_value = extracted_data.get(feedback.field)

    correction = add_correction(
        job_id=job_id,
        field=feedback.field,
        wrong_value=wrong_value,
        correct_value=feedback.correct_value,
        raw_text=job.get("full_text", ""),
        extracted_data=extracted_data,
    )

    logger.info(f"Feedback submitted for job {job_id}: {feedback.field}")

    return {
        "status": "saved",
        "correction_id": correction["id"],
        "feedback_count": get_feedback_stats()["total_corrections"],
    }


@app.get("/v1/training-data/export", summary="Export training dataset")
async def export_training_data():
    """
    Export feedback corrections as JSONL for model fine-tuning.

    Returns a JSONL file with training examples.
    """
    filepath = export_training_jsonl()

    with open(filepath, encoding="utf-8") as f:
        content = f.read()

    logger.info(f"Training data exported: {filepath}")

    return Response(
        content=content,
        media_type="application/jsonl",
        headers={"Content-Disposition": "attachment; filename=training_data.jsonl"},
    )


@app.get("/v1/feedback/stats", summary="Get feedback statistics")
async def feedback_stats():
    """
    Get statistics about submitted feedback corrections.
    """
    return get_feedback_stats()


@app.get("/health", summary="Health check")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "factura-ai"}
