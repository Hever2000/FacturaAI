from fastapi.testclient import TestClient


def test_health_check():
    """Test health check endpoint."""
    from src.api.main import app

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["service"] == "zenith-ocr"


def test_job_not_found():
    """Test 404 for non-existent job."""
    from src.api.main import app

    client = TestClient(app)
    response = client.get("/v1/jobs/nonexistent-job-id")

    assert response.status_code == 404
    assert response.json()["detail"] == "Job not found"


def test_export_not_processed():
    """Test 400 for unprocessed job export."""
    from src.api.main import app, jobs_db

    client = TestClient(app)

    job_id = "test-pending-job"
    jobs_db[job_id] = {"id": job_id, "status": "PENDING", "filename": "test.png"}

    response = client.get(f"/v1/jobs/{job_id}/export")
    assert response.status_code == 400
    assert response.json()["detail"] == "Job not yet processed"


def test_export_job_not_found():
    """Test 404 for export of non-existent job."""
    from src.api.main import app

    client = TestClient(app)
    response = client.get("/v1/jobs/nonexistent/export")

    assert response.status_code == 404


def test_job_status():
    """Test job status endpoint with processed job."""
    from src.api.main import app, jobs_db

    client = TestClient(app)

    job_id = "test-job-status"
    jobs_db[job_id] = {
        "id": job_id,
        "status": "PROCESSED",
        "filename": "test.png",
        "extracted_data": {"invoice_number": "123"},
    }

    response = client.get(f"/v1/jobs/{job_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "PROCESSED"
    assert response.json()["extracted_data"]["invoice_number"] == "123"


def test_job_status_with_raw_text():
    """Test job status with OCR raw text."""
    from src.api.main import app, jobs_db

    client = TestClient(app)

    job_id = "test-job-raw-text"
    jobs_db[job_id] = {
        "id": job_id,
        "status": "PROCESSED",
        "filename": "invoice.png",
        "raw_text": [{"text": "Invoice #123", "confidence": 0.99}],
        "full_text": "Invoice #123",
        "extracted_data": {"invoice_number": "123"},
    }

    response = client.get(f"/v1/jobs/{job_id}")
    assert response.status_code == 200
    data = response.json()
    assert "raw_text" in data
    assert len(data["raw_text"]) == 1


def test_process_job_missing_file():
    """Test process endpoint without file."""
    from src.api.main import app

    client = TestClient(app)
    response = client.post("/v1/process")

    assert response.status_code == 422


def test_api_docs():
    """Test API docs endpoint."""
    from src.api.main import app

    client = TestClient(app)
    response = client.get("/docs")

    assert response.status_code == 200


def test_job_status_failed():
    """Test job status with failed job."""
    from src.api.main import app, jobs_db

    client = TestClient(app)

    job_id = "test-job-failed"
    jobs_db[job_id] = {
        "id": job_id,
        "status": "FAILED",
        "filename": "test.png",
        "error": "OCR processing failed",
    }

    response = client.get(f"/v1/jobs/{job_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "FAILED"
    assert response.json()["error"] == "OCR processing failed"
