import base64
import logging
import os
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger("facturaai")

try:
    import easyocr

    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False


class OCRService:
    """Service for OCR processing with multiple providers."""

    def __init__(self):
        self.paddle_vl_api_url = os.getenv(
            "PADDLE_VL_API_URL",
            "https://c6vceb62c4n8zfaf.aistudio-app.com/layout-parsing"
        )
        self.paddle_vl_token = os.getenv(
            "PADDLE_VL_TOKEN",
            "916d29311a347cb06a2e3b1daa41403f4fc4d7b9"
        )

    def _create_session_with_retries(self) -> requests.Session:
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

    def process_easyocr(self, file_path: str) -> dict[str, Any]:
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

    def process_paddle(self, file_path: str) -> dict[str, Any]:
        """Process image with PaddleOCR-VL remote API."""
        logger.info(f"Starting PaddleOCR-VL for file: {file_path}")

        session = self._create_session_with_retries()

        try:
            with open(file_path, "rb") as file:
                file_bytes = file.read()
                file_data = base64.b64encode(file_bytes).decode("ascii")

            headers = {
                "Authorization": f"token {self.paddle_vl_token}",
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
            response = session.post(
                self.paddle_vl_api_url,
                json=payload,
                headers=headers,
                timeout=180
            )

            if response.status_code != 200:
                logger.warning(
                    f"PaddleOCR-VL API error: {response.status_code}, "
                    "trying EasyOCR fallback"
                )
                return self.process_easyocr(file_path)

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
            return self.process_easyocr(file_path)
        except Exception as e:
            logger.warning(f"PaddleOCR-VL failed: {str(e)}, trying EasyOCR fallback")
            return self.process_easyocr(file_path)

    def process(self, file_path: str) -> dict[str, Any]:
        """
        Process image with OCR. Tries PaddleOCR-VL first, falls back to EasyOCR.

        Args:
            file_path: Path to the image file

        Returns:
            Dictionary with raw_text, full_text, status, and ocr_engine
        """
        return self.process_paddle(file_path)
