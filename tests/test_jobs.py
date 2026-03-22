"""Tests for job processing endpoints."""

import io
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from src.models.job import Job
from src.models.user import User


@pytest.mark.asyncio
async def test_process_requires_auth(client: AsyncClient):
    """Test /jobs/process requires authentication."""
    response = await client.post("/v1/jobs/process")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_process_invoice_success(
    auth_client: AsyncClient,
    db_session,
    test_user,
    mock_ocr_result,
    mock_llm_extraction,
    temp_storage,
):
    """Test successful invoice processing."""
    with (
        patch("src.api.v1.jobs.process_ocr", return_value=mock_ocr_result),
        patch("src.api.v1.jobs.extract_invoice_fields", return_value=mock_llm_extraction),
    ):

        file_content = b"fake image content"
        files = {"file": ("invoice.png", io.BytesIO(file_content), "image/png")}

        response = await auth_client.post("/v1/jobs/process", files=files)
        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert data["status"] == "completed"

        # Verify job was saved to DB
        result = await db_session.execute(select(Job).where(Job.user_id == test_user.id))
        job = result.scalar_one()
        assert job.user_id == test_user.id
        assert job.filename == "invoice.png"
        assert job.extracted_data is not None


@pytest.mark.asyncio
async def test_process_invoice_unsupported_type(
    auth_client: AsyncClient,
):
    """Test processing rejects unsupported file types."""
    file_content = b"not an image"
    files = {"file": ("document.exe", io.BytesIO(file_content), "application/octet-stream")}

    response = await auth_client.post("/v1/jobs/process", files=files)
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


@pytest.mark.asyncio
async def test_process_invoice_ocr_failure(
    auth_client: AsyncClient,
    mock_ocr_result,
    temp_storage,
):
    """Test handling of OCR failure."""
    failed_ocr = {**mock_ocr_result, "status": "OCR_FAILED", "error": "Image unreadable"}

    with patch("src.api.v1.jobs.process_ocr", return_value=failed_ocr):

        files = {"file": ("bad.png", io.BytesIO(b"x"), "image/png")}
        response = await auth_client.post("/v1/jobs/process", files=files)
        assert response.status_code == 500
        assert "OCR processing failed" in response.json()["detail"]


@pytest.mark.asyncio
async def test_process_invoice_llm_failure(
    auth_client: AsyncClient,
    mock_ocr_result,
    temp_storage,
):
    """Test handling of LLM extraction failure."""
    with (
        patch("src.api.v1.jobs.process_ocr", return_value=mock_ocr_result),
        patch("src.api.v1.jobs.extract_invoice_fields", return_value={"error": "LLM unavailable"}),
    ):

        files = {"file": ("inv.png", io.BytesIO(b"x"), "image/png")}
        response = await auth_client.post("/v1/jobs/process", files=files)
        assert response.status_code == 500


@pytest.mark.asyncio
async def test_list_jobs(auth_client: AsyncClient, test_user, db_session):
    """Test listing jobs with pagination."""
    # Create a few jobs
    for i in range(3):
        job = Job(
            user_id=test_user.id,
            status="completed",
            filename=f"invoice_{i}.png",
            extracted_data={"total": 100.0 * (i + 1)},
        )
        db_session.add(job)
    await db_session.commit()

    response = await auth_client.get("/v1/jobs")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 3
    assert data["page"] == 1
    assert data["page_size"] == 20
    assert len(data["jobs"]) >= 3


@pytest.mark.asyncio
async def test_list_jobs_filter_by_status(auth_client: AsyncClient, test_user, db_session):
    """Test filtering jobs by status."""
    job = Job(user_id=test_user.id, status="failed", filename="failed.png")
    db_session.add(job)
    await db_session.commit()

    response = await auth_client.get("/v1/jobs?status_filter=failed")
    assert response.status_code == 200
    data = response.json()
    for j in data["jobs"]:
        assert j["status"] == "failed"


@pytest.mark.asyncio
async def test_list_jobs_pagination(auth_client: AsyncClient, test_user, db_session):
    """Test job list pagination."""
    response = await auth_client.get("/v1/jobs?page=1&page_size=2")
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 1
    assert data["page_size"] == 2


@pytest.mark.asyncio
async def test_get_job_success(
    auth_client: AsyncClient, test_user, db_session, mock_llm_extraction
):
    """Test getting a specific job."""
    job = Job(
        user_id=test_user.id,
        status="completed",
        filename="test.png",
        ocr_engine="paddleocr",
        extracted_data=mock_llm_extraction,
        raw_text='{"text": "FACTURA A"}',
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    response = await auth_client.get(f"/v1/jobs/{job.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["filename"] == "test.png"
    assert data["ocr_engine"] == "paddleocr"
    assert data["extracted_data"] is not None


@pytest.mark.asyncio
async def test_get_job_not_found(auth_client: AsyncClient):
    """Test getting a non-existent job."""
    from uuid import uuid4

    response = await auth_client.get(f"/v1/jobs/{uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_other_user_job_fails(auth_client: AsyncClient, client: AsyncClient, db_session):
    """Test getting another user's job fails."""
    from src.core.security import get_password_hash

    # Create another user with a job
    other_user = User(
        email="other@test.com",
        hashed_password=get_password_hash("Pass123!"),
        is_active=True,
    )
    db_session.add(other_user)
    await db_session.commit()

    job = Job(user_id=other_user.id, status="completed", filename="other.png")
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    # Try to access with first user's token
    response = await auth_client.get(f"/v1/jobs/{job.id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_export_job_json(
    auth_client: AsyncClient, test_user, db_session, mock_llm_extraction
):
    """Test exporting job as JSON."""
    job = Job(
        user_id=test_user.id,
        status="completed",
        filename="export_test.png",
        extracted_data=mock_llm_extraction,
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    response = await auth_client.get(f"/v1/jobs/{job.id}/export?format=json")
    assert response.status_code == 200
    assert "application/json" in response.headers["content-type"]
    data = response.json()
    assert data["filename"] == "export_test.png"
    assert data["invoice_data"] is not None


@pytest.mark.asyncio
async def test_export_job_txt(auth_client: AsyncClient, test_user, db_session, mock_llm_extraction):
    """Test exporting job as plain text."""
    job = Job(
        user_id=test_user.id,
        status="completed",
        filename="text_test.png",
        extracted_data=mock_llm_extraction,
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    response = await auth_client.get(f"/v1/jobs/{job.id}/export?format=txt")
    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    content = response.text
    assert "FACTURA PROCESADA" in content
    assert "Acme SA" in content


@pytest.mark.asyncio
async def test_export_unprocessed_job(auth_client: AsyncClient, test_user, db_session):
    """Test exporting an unprocessed job fails."""
    job = Job(user_id=test_user.id, status="processing", filename="pending.png")
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    response = await auth_client.get(f"/v1/jobs/{job.id}/export")
    assert response.status_code == 400
    assert "not yet processed" in response.json()["detail"]


@pytest.mark.asyncio
async def test_feedback_success(
    auth_client: AsyncClient, test_user, db_session, mock_llm_extraction
):
    """Test submitting feedback for a job."""
    job = Job(
        user_id=test_user.id,
        status="completed",
        filename="feedback_test.png",
        extracted_data=mock_llm_extraction,
        raw_text="Some raw text from OCR",
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    response = await auth_client.post(
        f"/v1/jobs/{job.id}/feedback",
        json={"field": "razon_social_vendedor", "correct_value": "Corrected Name"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "saved"
    assert "feedback_id" in data


@pytest.mark.asyncio
async def test_feedback_nested_field(
    auth_client: AsyncClient, test_user, db_session, mock_llm_extraction
):
    """Test feedback for nested item field."""
    job = Job(
        user_id=test_user.id,
        status="completed",
        filename="nested_feedback.png",
        extracted_data=mock_llm_extraction,
    )
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    response = await auth_client.post(
        f"/v1/jobs/{job.id}/feedback",
        json={"field": "items.0.descripcion", "correct_value": "Corrected Description"},
    )
    assert response.status_code == 200
