import logging
import os
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("zenith_ocr")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
if not GROQ_API_KEY:
    logger.warning("GROQ_API_KEY not set in environment variables")


def process_ocr(file_path: str) -> Dict[str, Any]:
    """Process image with EasyOCR and extract text."""
    import easyocr

    logger.info(f"Starting OCR for file: {file_path}")

    reader = easyocr.Reader(["en", "es"], gpu=False, verbose=False)
    result = reader.readtext(file_path)

    extracted_text = []
    for detection in result:
        text = detection[1]
        confidence = detection[2]
        extracted_text.append({"text": text, "confidence": confidence})

    full_text = " ".join([item["text"] for item in extracted_text])

    logger.info(f"OCR completed, extracted {len(extracted_text)} text segments")

    return {"raw_text": extracted_text, "full_text": full_text, "status": "OCR_COMPLETED"}


def extract_invoice_fields(full_text: str) -> Dict[str, Any]:
    """Extract structured invoice data using Groq LLM."""
    from groq import Groq

    if not GROQ_API_KEY:
        logger.error("GROQ_API_KEY not configured")
        return {"error": "GROQ_API_KEY not configured"}

    logger.info("Starting LLM extraction for invoice fields")

    client = Groq(api_key=GROQ_API_KEY)

    prompt = f"""Eres un asistente especializado en extraer información de facturas.

Extrae los siguientes campos del texto de factura y devuelve SOLO un JSON válido:

{{
    "invoice_number": "número de factura",
    "issue_date": "fecha de emisión en formato YYYY-MM-DD",
    "due_date": "fecha de vencimiento en formato YYYY-MM-DD",
    "vendor_name": "nombre del vendedor/razón social",
    "vendor_cuit": "CUIT del vendedor (formato XX-XXXXXXXX-X)",
    "vendor_address": "domicilio del vendedor",
    "vendor_condition": "condición IVA del vendedor",
    "customer_name": "nombre del cliente",
    "customer_cuit": "CUIT del cliente",
    "customer_address": "domicilio del cliente",
    "subtotal": "subtotal sin IVA",
    "tax_amount": "monto del IVA",
    "total": "total de la factura",
    "items": [
        {{
            "description": "descripción del producto/servicio",
            "quantity": cantidad,
            "unit_price": precio unitario,
            "amount": importe total
        }}
    ],
    "payment_condition": "condición de venta (ej: Cuenta Corriente, Contado)",
    "invoice_type": "tipo de factura (ej: A, B, C)"
}}

Texto de la factura:
{full_text}

Responde ONLY con el JSON, sin texto adicional."""

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )

        text = response.choices[0].message.content
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]

        import json

        extracted = json.loads(text.strip())

        logger.info("LLM extraction completed successfully")
        return extracted

    except Exception as e:
        logger.error(f"LLM extraction failed: {str(e)}")
        return {"error": f"Failed to parse LLM response: {str(e)}"}
