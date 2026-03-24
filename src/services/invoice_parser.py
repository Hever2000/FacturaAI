import logging
from typing import Any

from src.services.llm_service import LLMService
from src.services.ocr_service import OCRService

logger = logging.getLogger("facturaai")


class InvoiceParserService:
    """Service that orchestrates OCR + LLM for invoice processing."""

    def __init__(self):
        self.ocr_service = OCRService()
        self.llm_service = LLMService()

    def process(self, file_path: str) -> dict[str, Any]:
        """
        Process an invoice image through OCR and LLM extraction.

        Args:
            file_path: Path to the invoice image file

        Returns:
            Dictionary with:
            - status: "completed" or "failed"
            - ocr_engine: Name of OCR engine used
            - raw_text: Raw OCR text blocks
            - extracted_data: Structured invoice data from LLM
            - error: Error message if failed
        """
        logger.info(f"Starting invoice processing for: {file_path}")

        ocr_result = self.ocr_service.process(file_path)

        if "error" in ocr_result or ocr_result.get("status") == "OCR_FAILED":
            error_msg = ocr_result.get("error", "Unknown OCR error")
            logger.error(f"OCR failed: {error_msg}")
            return {
                "status": "failed",
                "error": f"OCR failed: {error_msg}",
                "ocr_engine": ocr_result.get("ocr_engine", "unknown"),
            }

        extracted_data = self.llm_service.extract_invoice_fields(
            ocr_result["full_text"]
        )

        if "error" in extracted_data:
            error_msg = extracted_data.get("error", "Unknown LLM error")
            logger.error(f"LLM extraction failed: {error_msg}")
            return {
                "status": "failed",
                "error": f"LLM extraction failed: {error_msg}",
                "ocr_engine": ocr_result.get("ocr_engine"),
                "raw_text": ocr_result.get("raw_text"),
            }

        logger.info("Invoice processing completed successfully")

        return {
            "status": "completed",
            "ocr_engine": ocr_result.get("ocr_engine"),
            "raw_text": ocr_result.get("raw_text"),
            "full_text": ocr_result.get("full_text"),
            "extracted_data": extracted_data,
            "confidence_score": extracted_data.get("confidence_score", 0.8),
        }
