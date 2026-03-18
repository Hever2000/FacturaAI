import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    from src.api.main import app

    return TestClient(app)


@pytest.fixture
def mock_ocr_result():
    """Mock OCR result for testing."""
    return {
        "raw_text": [{"text": "Test Invoice #123", "confidence": 0.99}],
        "full_text": "Test Invoice #123",
        "status": "OCR_COMPLETED",
    }


@pytest.fixture
def mock_llm_result():
    """Mock LLM extraction result for testing."""
    return {
        "invoice_number": "001-00012345",
        "vendor_name": "Test Vendor SA",
        "vendor_cuit": "20-12345678-9",
        "total": 1500.00,
        "invoice_type": "A",
    }
