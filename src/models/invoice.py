from enum import Enum

from pydantic import BaseModel, Field


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

    item_numero: int | None = Field(None, description="Número de línea/item")
    codigo: str | None = Field(None, description="Código del producto/servicio")
    descripcion: str = Field(..., description="Descripción del producto o servicio")
    cantidad: float = Field(default=1.0, ge=0, description="Cantidad")
    unidad_medida: str | None = Field(None, description="Unidad de medida (ej: unidades, hs, kg)")
    precio_unitario: float = Field(default=0.0, ge=0, description="Precio unitario sin IVA")
    subtotal_item: float = Field(..., ge=0, description="Subtotal del item (precio * cantidad)")
    total_item: float = Field(..., ge=0, description="Total del item (con/donde aplique IVA)")
    alicuota_iva: str | None = Field(None, description="Alicuota de IVA (0%, 5%, 10.5%, 21%, 27%)")
    importe_iva: float | None = Field(default=0.0, ge=0, description="Importe de IVA del item")
    bonificacion: float | None = Field(
        default=0.0, ge=0, description="Bonificación/descuento del item"
    )


class InvoiceData(BaseModel):
    """Structured Argentine invoice data extracted by LLM."""

    codigo_factura: str | None = Field(
        None, description="Código único de la factura (interno del sistema)"
    )

    punto_de_venta: str = Field(..., description="Punto de venta (4 dígitos)")
    numero_comprobante: str = Field(..., description="Número de comprobante")
    tipo_comprobante: str = Field(
        ..., description="Tipo (FC=Factura, ND=Nota Débito, NC=Nota Crédito)"
    )
    letra_comprobante: str | None = Field(None, description="Letra (A, B, C, M)")

    fecha_emision: str = Field(..., description="Fecha de emisión (YYYY-MM-DD)")
    fecha_vencimiento_pago: str | None = Field(
        None, description="Fecha de vencimiento para el pago (YYYY-MM-DD)"
    )

    periodo_desde: str | None = Field(None, description="Período facturado desde (YYYY-MM-DD)")
    periodo_hasta: str | None = Field(None, description="Período facturado hasta (YYYY-MM-DD)")

    cae: str | None = Field(None, description="Código de Autorización de Emisión (CAE)")
    fecha_vencimiento_cae: str | None = Field(
        None, description="Fecha de vencimiento del CAE (YYYY-MM-DD)"
    )

    razon_social_vendedor: str = Field(..., description="Razón Social del vendedor")
    vendedor_cuit: str = Field(..., description="CUIT del vendedor (formato XX-XXXXXXXX-X)")
    vendedor_condicion_iva: str = Field(..., description="Condición frente al IVA del vendedor")
    vendedor_ingresos_brutos: str | None = Field(
        None, description="Número de Inscripción en Ingresos Brutos"
    )
    vendedor_domicilio: str | None = Field(None, description="Domicilio comercial del vendedor")
    vendedor_localidad: str | None = Field(None, description="Localidad y CP del vendedor")

    razon_social_cliente: str = Field(..., description="Razón Social del cliente")
    cliente_cuit: str = Field(..., description="CUIT del cliente (formato XX-XXXXXXXX-X)")
    cliente_condicion_iva: str = Field(..., description="Condición frente al IVA del cliente")
    cliente_domicilio: str | None = Field(None, description="Domicilio del cliente")
    cliente_localidad: str | None = Field(None, description="Localidad y CP del cliente")

    subtotal: float = Field(
        default=0.0, ge=0, description="Subtotal (suma de neto gravado + neto no gravado)"
    )
    total: float = Field(default=0.0, ge=0, description="Importe total del comprobante")

    importe_neto_gravado: float = Field(default=0.0, ge=0, description="Importe neto gravado")
    importe_neto_no_gravado: float = Field(default=0.0, ge=0, description="Importe neto no gravado")
    importe_exento: float = Field(default=0.0, ge=0, description="Importe exento")

    iva_27: float = Field(default=0.0, ge=0, description="IVA al 27%")
    iva_21: float = Field(default=0.0, ge=0, description="IVA al 21%")
    iva_10_5: float = Field(default=0.0, ge=0, description="IVA al 10.5%")
    iva_5: float = Field(default=0.0, ge=0, description="IVA al 5%")
    iva_2_5: float = Field(default=0.0, ge=0, description="IVA al 2.5%")
    iva_0: float = Field(default=0.0, ge=0, description="IVA al 0%")

    total_iva: float = Field(default=0.0, ge=0, description="Total de IVA (suma de todos los IVA)")

    importe_otros_tributos: float = Field(
        default=0.0, ge=0, description="Importe de Otros Tributos"
    )
    total_tributos: float = Field(default=0.0, ge=0, description="Total Otros Tributos")

    condicion_pago: str = Field(
        ..., description="Condición de pago (Contado, Cuenta Corriente, Tarjeta, etc.)"
    )

    items: list[InvoiceItem] = Field(
        default_factory=list, description="Detalle de items de la factura"
    )

    observaciones: str | None = Field(None, description="Observaciones o notas adicionales")


class JobResponse(BaseModel):
    """Job processing response."""

    job_id: str
    status: str


class JobDetail(BaseModel):
    """Full job details."""

    id: str
    status: str
    filename: str | None = None
    raw_text: list[dict] | None = None
    full_text: str | None = None
    extracted_data: dict | None = None
    error: str | None = None
