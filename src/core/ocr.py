import base64
import json
import logging
import os
from typing import Any, Dict

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("zenith_ocr")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
PADDLE_VL_API_URL = os.getenv(
    "PADDLE_VL_API_URL", "https://c6vceb62c4n8zfaf.aistudio-app.com/layout-parsing"
)
PADDLE_VL_TOKEN = os.getenv(
    "PADDLE_VL_TOKEN", "916d29311a347cb06a2e3b1daa41403f4fc4d7b9"
)

if not GROQ_API_KEY:
    logger.warning("GROQ_API_KEY not set in environment variables")


def process_ocr(file_path: str) -> Dict[str, Any]:
    """Process image with PaddleOCR-VL remote API."""
    logger.info(f"Starting PaddleOCR-VL for file: {file_path}")

    try:
        with open(file_path, "rb") as file:
            file_bytes = file.read()
            file_data = base64.b64encode(file_bytes).decode("ascii")

        headers = {
            "Authorization": f"token {PADDLE_VL_TOKEN}",
            "Content-Type": "application/json",
        }

        required_payload = {"file": file_data, "fileType": 1}

        optional_payload = {
            "useDocOrientationClassify": False,
            "useDocUnwarping": False,
            "useChartRecognition": False,
        }

        payload = {**required_payload, **optional_payload}

        response = requests.post(
            PADDLE_VL_API_URL, json=payload, headers=headers, timeout=60
        )

        if response.status_code != 200:
            logger.error(f"PaddleOCR-VL API error: {response.status_code}")
            return {
                "error": f"API returned status {response.status_code}",
                "status": "OCR_FAILED",
            }

        result = response.json()["result"]
        layout_results = result.get("layoutParsingResults", [])

        extracted_text = []
        for i, res in enumerate(layout_results):
            md_text = res.get("markdown", {}).get("text", "")
            if md_text:
                extracted_text.append({"text": md_text, "confidence": 1.0, "block": i})

        full_text = " ".join([item["text"] for item in extracted_text])

        logger.info(
            f"PaddleOCR-VL completed, extracted {len(extracted_text)} text blocks"
        )

        return {
            "raw_text": extracted_text,
            "full_text": full_text,
            "status": "OCR_COMPLETED",
        }

    except Exception as e:
        logger.error(f"PaddleOCR-VL failed: {str(e)}")
        return {"error": str(e), "status": "OCR_FAILED"}


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

        extracted = json.loads(text.strip())

        logger.info("LLM extraction completed successfully")
        return extracted

    except Exception as e:
        logger.error(f"LLM extraction failed: {str(e)}")
        return {"error": f"Failed to parse LLM response: {str(e)}"}
