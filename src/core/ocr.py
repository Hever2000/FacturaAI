import base64
import json
import logging
import os
from typing import Any, Dict

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    import easyocr

    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False

load_dotenv()

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("factura_ai")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
PADDLE_VL_API_URL = os.getenv(
    "PADDLE_VL_API_URL", "https://c6vceb62c4n8zfaf.aistudio-app.com/layout-parsing"
)
PADDLE_VL_TOKEN = os.getenv("PADDLE_VL_TOKEN", "916d29311a347cb06a2e3b1daa41403f4fc4d7b9")

if not GROQ_API_KEY:
    logger.warning("GROQ_API_KEY not set in environment variables")


def create_session_with_retries() -> requests.Session:
    """Create a requests session with automatic retry logic."""
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def process_ocr_with_easyocr(file_path: str) -> Dict[str, Any]:
    """Process image with EasyOCR as fallback."""
    if not EASYOCR_AVAILABLE:
        logger.error("EasyOCR not installed")
        return {"error": "EasyOCR not installed", "status": "OCR_FAILED"}

    logger.info(f"Starting EasyOCR fallback for file: {file_path}")

    try:
        reader = easyocr.Reader(["en", "es"], gpu=False, verbose=False)
        results = reader.readtext(file_path)

        extracted_text = []
        for i, (_bbox, text, confidence) in enumerate(results):
            if text.strip():
                extracted_text.append(
                    {
                        "text": text.strip(),
                        "confidence": confidence if confidence else 1.0,
                        "block": i,
                    }
                )

        full_text = " ".join([item["text"] for item in extracted_text])

        logger.info(f"EasyOCR completed, extracted {len(extracted_text)} text blocks")

        return {
            "raw_text": extracted_text,
            "full_text": full_text,
            "status": "OCR_COMPLETED",
            "ocr_engine": "easyocr",
        }

    except Exception as e:
        logger.error(f"EasyOCR failed: {str(e)}")
        return {"error": str(e), "status": "OCR_FAILED"}


def process_ocr(file_path: str) -> Dict[str, Any]:
    """Process image with PaddleOCR-VL remote API, with EasyOCR as fallback."""
    logger.info(f"Starting PaddleOCR-VL for file: {file_path}")

    session = create_session_with_retries()

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

        logger.info("Sending request to PaddleOCR-VL API...")
        response = session.post(PADDLE_VL_API_URL, json=payload, headers=headers, timeout=180)

        if response.status_code != 200:
            logger.warning(
                f"PaddleOCR-VL API error: {response.status_code}, " "trying EasyOCR fallback"
            )
            return process_ocr_with_easyocr(file_path)

        result = response.json()["result"]
        layout_results = result.get("layoutParsingResults", [])

        extracted_text = []
        for i, res in enumerate(layout_results):
            md_text = res.get("markdown", {}).get("text", "")
            if md_text:
                extracted_text.append({"text": md_text, "confidence": 1.0, "block": i})

        full_text = " ".join([item["text"] for item in extracted_text])

        logger.info(f"PaddleOCR-VL completed, extracted {len(extracted_text)} text blocks")

        return {
            "raw_text": extracted_text,
            "full_text": full_text,
            "status": "OCR_COMPLETED",
            "ocr_engine": "paddleocr",
        }

    except requests.exceptions.Timeout:
        logger.warning("PaddleOCR-VL timeout, trying EasyOCR fallback")
        return process_ocr_with_easyocr(file_path)
    except Exception as e:
        logger.warning(f"PaddleOCR-VL failed: {str(e)}, trying EasyOCR fallback")
        return process_ocr_with_easyocr(file_path)


def extract_invoice_fields(full_text: str) -> Dict[str, Any]:
    """Extract structured invoice data using Groq LLM."""
    from groq import Groq

    if not GROQ_API_KEY:
        logger.error("GROQ_API_KEY not configured")
        return {"error": "GROQ_API_KEY not configured"}

    logger.info("Starting LLM extraction for Argentine invoice fields")

    client = Groq(api_key=GROQ_API_KEY)

    prompt = (
        "Eres un asistente especializado en extraer información de facturas "
        "argentinas (sistema de facturación AFIP).\n\n"
        "Analiza el texto de la factura y extrae TODOS los campos disponibles. "
        "Devuelve SOLO un JSON válido con esta estructura exacta:\n\n"
        "{\n"
        '    "codigo_factura": "Código único de la factura (si existe en el documento)",\n\n'
        '    "punto_de_venta": "Código de punto de venta (4 dígitos, ej: 0001)",\n'
        '    "numero_comprobante": "Número de comprobante (ej: 00001293)",\n'
        '    "tipo_comprobante": "Tipo (FC=Factura, ND=Nota Débito, NC=Nota Crédito)",\n'
        '    "letra_comprobante": "Letra (A, B, C o M para mixtas)",\n\n'
        '    "fecha_emision": "Fecha de emisión (YYYY-MM-DD)",\n'
        '    "fecha_vencimiento_pago": "Fecha de vencimiento para el pago (YYYY-MM-DD)",\n\n'
        '    "periodo_desde": "Período facturado desde (YYYY-MM-DD si existe)",\n'
        '    "periodo_hasta": "Período facturado hasta (YYYY-MM-DD si existe)",\n\n'
        '    "cae": "Código de Autorización de Emisión (CAE - 14 dígitos si existe)",\n'
        '    "fecha_vencimiento_cae": "Fecha de vencimiento del CAE (YYYY-MM-DD si existe)",\n\n'
        '    "razon_social_vendedor": "Razón Social del vendedor",\n'
        '    "vendedor_cuit": "CUIT del vendedor (formato XX-XXXXXXXX-X)",\n'
        '    "vendedor_condicion_iva": "Condición frente al IVA del vendedor '
        '(IVA Responsable Inscripto, IVA Sujeto Exento, Consumidor Final, etc.)",\n'
        '    "vendedor_ingresos_brutos": "Número de Inscripción en Ingresos Brutos (si existe)",\n'
        '    "vendedor_domicilio": "Domicilio comercial del vendedor",\n'
        '    "vendedor_localidad": "Localidad y CP del vendedor",\n\n'
        '    "razon_social_cliente": "Razón Social del cliente",\n'
        '    "cliente_cuit": "CUIT del cliente (formato XX-XXXXXXXX-X)",\n'
        '    "cliente_condicion_iva": "Condición frente al IVA del cliente",\n'
        '    "cliente_domicilio": "Domicilio del cliente",\n'
        '    "cliente_localidad": "Localidad y CP del cliente",\n\n'
        '    "subtotal": 0.00,\n'
        '    "total": 0.00,\n\n'
        '    "importe_neto_gravado": 0.00,\n'
        '    "importe_neto_no_gravado": 0.00,\n'
        '    "importe_exento": 0.00,\n\n'
        '    "iva_27": 0.00,\n'
        '    "iva_21": 0.00,\n'
        '    "iva_10_5": 0.00,\n'
        '    "iva_5": 0.00,\n'
        '    "iva_2_5": 0.00,\n'
        '    "iva_0": 0.00,\n\n'
        '    "total_iva": 0.00,\n\n'
        '    "importe_otros_tributos": 0.00,\n'
        '    "total_tributos": 0.00,\n\n'
        '    "condicion_pago": "Condición de pago (Contado, Cuenta Corriente, '
        'Tarjeta de Débito, etc.)",\n\n'
        '    "items": [\n'
        "        {\n"
        '            "item_numero": 1,\n'
        '            "codigo": "Código del producto/servicio (si existe)",\n'
        '            "descripcion": "Descripción completa del producto/servicio",\n'
        '            "cantidad": 1.0,\n'
        '            "unidad_medida": "Unidad de medida (ej: unidades, hs, kg - si existe)",\n'
        '            "precio_unitario": 0.00,\n'
        '            "subtotal_item": 0.00,\n'
        '            "total_item": 0.00,\n'
        '            "alicuota_iva": "0%, 5%, 10.5%, 21% o 27% (si existe)",\n'
        '            "importe_iva": 0.00,\n'
        '            "bonificacion": 0.00\n'
        "        }\n"
        "    ],\n\n"
        '    "observaciones": "Observaciones o notas adicionales (si existen)"\n'
        "}\n\n"
        "REGLAS IMPORTANTES:\n"
        "- Usa punto (.) como separador decimal\n"
        "- Todos los montos deben ser números (no strings con $, "
        "comas separadoras de miles, etc.)\n"
        "- Los campos que NO aparezcan en el documento deben ser null (strings) o 0 (números)\n"
        "- El CUIT debe tener el formato XX-XXXXXXXX-X con guiones\n"
        "- La suma de iva_0 + iva_5 + iva_10_5 + iva_21 + iva_27 debe ser igual a total_iva\n"
        "- subtotal + total_iva + total_tributos debe aproximarse a total\n"
        "- Si hay varios items, incluye TODOS en el array 'items'\n"
        "- El campo 'total_item' de cada item debe incluir el subtotal + IVA "
        "del item (o el total de la línea)\n"
        "- El campo 'subtotal_item' es el importe sin IVA\n\n"
        "Texto de la factura a analizar:\n"
        f"{full_text}\n\n"
        "Responde ONLY con el JSON, sin texto adicional."
    )

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )

        text = response.choices[0].message.content or ""
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
