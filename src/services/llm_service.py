import json
import logging
import os
from typing import Any

from groq import Groq

logger = logging.getLogger("facturaai")


class LLMService:
    """Service for LLM-based invoice field extraction."""

    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY", "")
        self.model = "llama-3.3-70b-versatile"

        if not self.api_key:
            logger.warning("GROQ_API_KEY not configured")

    def _normalize_numeric_fields(self, data: dict[str, Any]) -> dict[str, Any]:
        """Normalize numeric fields from Argentine format to standard Python numbers."""
        import re

        def parse_argentine_number(value: str | int | float | None) -> float | int | None:
            if value is None:
                return None
            if isinstance(value, (int, float)):
                return float(value)
            if not isinstance(value, str):
                return None

            value = value.strip()
            if not value:
                return None

            value = re.sub(r"[$€£¥₹\s]", "", value)

            if re.search(r"\d{1,3}(\.\d{3})+,\d+$", value):
                value = value.replace(".", "").replace(",", ".")
                try:
                    return float(value)
                except ValueError:
                    return None

            if "," in value and "." not in value:
                value = value.replace(",", ".")
                try:
                    return float(value)
                except ValueError:
                    return None

            try:
                return float(value)
            except ValueError:
                return None

        numeric_fields = [
            "subtotal", "total", "importe_neto_gravado",
            "importe_neto_no_gravado", "importe_exento",
            "iva_27", "iva_21", "iva_10_5", "iva_5", "iva_2_5", "iva_0",
            "total_iva", "importe_otros_tributos", "total_tributos",
            "precio_unitario", "subtotal_item", "total_item",
            "importe_iva", "bonificacion", "cantidad",
        ]

        result = data.copy()

        for field in numeric_fields:
            if field in result:
                result[field] = parse_argentine_number(result[field])

        if "items" in result and isinstance(result["items"], list):
            for i, item in enumerate(result["items"]):
                if isinstance(item, dict):
                    for field in numeric_fields:
                        if field in item:
                            result["items"][i][field] = parse_argentine_number(item[field])

        return result

    def _build_extraction_prompt(self, full_text: str) -> str:
        """Build the prompt for LLM invoice field extraction."""
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
            "- IMPORTANTE: Los montos de las facturas están en formato argentino:\n"
            "  * Punto (.) separa miles: 1.000 = mil, 1.000.000 = un millón\n"
            "  * Coma (,) es el separador decimal: 12,50 = doce pesos con cincuenta centavos\n"
            "  * Cuando veas '1.234,56' significa 'mil doscientos treinta y cuatro con 56/100'\n"
            "- Convierte todos los montos a NÚMEROS (float o int), sin símbolos de moneda\n"
            "- Usa punto (.) como separador decimal en el JSON de salida\n"
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

        return prompt

    def extract_invoice_fields(self, full_text: str) -> dict[str, Any]:
        """
        Extract structured invoice data using Groq LLM.

        Args:
            full_text: OCR-extracted text from the invoice image

        Returns:
            Dictionary with extracted invoice fields
        """
        if not self.api_key:
            logger.error("GROQ_API_KEY not configured")
            return {"error": "GROQ_API_KEY not configured"}

        logger.info("Starting LLM extraction for Argentine invoice fields")

        client = Groq(api_key=self.api_key)

        prompt = self._build_extraction_prompt(full_text)

        try:
            response = client.chat.completions.create(
                model=self.model,
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

            extracted = self._normalize_numeric_fields(extracted)

            logger.info("LLM extraction completed successfully")
            return extracted

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {str(e)}")
            return {"error": f"Failed to parse LLM response: {str(e)}"}
        except Exception as e:
            logger.error(f"LLM extraction failed: {str(e)}")
            return {"error": f"LLM extraction failed: {str(e)}"}
