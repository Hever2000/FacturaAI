from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum


class JobStatus(str, Enum):
    """Job processing status enum."""

    PENDING = "pending"
    PROCESSING_OCR = "processing_ocr"
    PROCESSING_LLM = "processing_llm"
    PENDING_REVIEW = "pending_review"
    PROCESSED = "processed"
    FAILED = "failed"


class InvoiceItem(BaseModel):
    """Individual invoice line item."""

    description: str = Field(..., description="Product or service description")
    quantity: float = Field(default=1.0, ge=0, description="Quantity")
    unit_price: float = Field(default=0.0, ge=0, description="Unit price")
    amount: float = Field(..., ge=0, description="Total amount")


class InvoiceData(BaseModel):
    """Structured invoice data extracted by LLM."""

    invoice_number: str = Field(..., description="Invoice number")
    issue_date: Optional[str] = Field(None, description="Issue date YYYY-MM-DD")
    due_date: Optional[str] = Field(None, description="Due date YYYY-MM-DD")

    vendor_name: str = Field(..., description="Vendor/ seller name")
    vendor_cuit: Optional[str] = Field(None, description="Vendor CUIT")
    vendor_address: Optional[str] = Field(None, description="Vendor address")
    vendor_condition: Optional[str] = Field(None, description="Vendor IVA condition")

    customer_name: Optional[str] = Field(None, description="Customer name")
    customer_cuit: Optional[str] = Field(None, description="Customer CUIT")
    customer_address: Optional[str] = Field(None, description="Customer address")

    subtotal: float = Field(default=0.0, ge=0, description="Subtotal without tax")
    tax_amount: float = Field(default=0.0, ge=0, description="Tax amount")
    total: float = Field(default=0.0, ge=0, description="Total amount")

    items: List[InvoiceItem] = Field(default_factory=list, description="Invoice items")

    payment_condition: Optional[str] = Field(None, description="Payment condition")
    invoice_type: Optional[str] = Field(None, description="Invoice type (A, B, C)")


class JobResponse(BaseModel):
    """Job processing response."""

    job_id: str
    status: str


class JobDetail(BaseModel):
    """Full job details."""

    id: str
    status: str
    filename: Optional[str] = None
    raw_text: Optional[List[dict]] = None
    full_text: Optional[str] = None
    extracted_data: Optional[dict] = None
    error: Optional[str] = None
