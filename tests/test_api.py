import pytest
from fastapi.testclient import TestClient


def test_health_check():
    """Test health check endpoint."""
    from src.api.main import app

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_job_not_found():
    """Test 404 for non-existent job."""
    from src.api.main import app

    client = TestClient(app)
    response = client.get("/v1/jobs/nonexistent-job-id")

    assert response.status_code == 404


def test_export_not_processed():
    """Test 400 for unprocessed job export."""
    from src.api.main import app, jobs_db

    client = TestClient(app)

    # Create a pending job
    job_id = "test-pending-job"
    jobs_db[job_id] = {"id": job_id, "status": "PENDING", "filename": "test.png"}

    response = client.get(f"/v1/jobs/{job_id}/export")
    assert response.status_code == 400


def test_job_status():
    """Test job status endpoint."""
    from src.api.main import app, jobs_db

    client = TestClient(app)

    # Create a processed job
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
