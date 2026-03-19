# FacturaAI

API para procesamiento de facturas argentinas utilizando OCR e IA. Extrae automáticamente datos estructurados de comprobantes y receipts.

## Características

- **OCR**: Extrae texto de imágenes de facturas usando PaddleOCR-VL
- **Extracción con IA**: Analiza datos estructurados usando Groq (Llama 3.3)
- **Exportación**: Descarga datos procesados en formato JSON
- **API REST**: Interfaz basada en FastAPI
- **Docker**: Listo para despliegue en producción

## Campos de Factura Soportados

- Número de factura, fecha de emisión, fecha de vencimiento
- Información del vendedor (nombre, CUIT, dirección, condición de IVA)
- Información del cliente (nombre, CUIT, dirección)
- Ítems de la línea (descripción, cantidad, precio, importe)
- Totales financieros (subtotal, impuestos, total)
- Condiciones de pago y tipo de factura

## Requisitos

- Python 3.12+
- Clave de API de Groq ([obtener aquí](https://console.groq.com/))

## Instalación

### Desarrollo Local

```bash
# Clonar el repositorio
git clone https://github.com/tuusuario/facturaai.git
cd facturaai

# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# o
venv\Scripts\activate  # Windows

# Instalar dependencias
pip install -r requirements.txt

# Configurar entorno
cp .env.example .env
# Editar .env y agregar tu GROQ_API_KEY

# Ejecutar el servidor
uvicorn src.api.main:app --reload
```

### Docker

```bash
# Construir y ejecutar con Docker
docker-compose up --build

# O construir manualmente
docker build -t facturaai .
docker run -p 8000:8000 -e GROQ_API_KEY=tu_clave facturaai
```

## Uso

### Endpoints de la API

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/v1/process` | POST | Subir factura para procesar |
| `/v1/jobs/{job_id}` | GET | Obtener estado del trabajo y resultados |
| `/v1/jobs/{job_id}/export` | GET | Exportar como archivo JSON |
| `/health` | GET | Verificación de salud |

### Ejemplo: Procesar Factura

```bash
# Subir factura
curl -X POST -F "file=@factura.png" http://localhost:8000/v1/process

# Respuesta:
# {"job_id": "abc-123", "status": "PROCESSED"}

# Obtener resultados
curl http://localhost:8000/v1/jobs/abc-123

# Exportar JSON
curl http://localhost:8000/v1/jobs/abc-123/export -o factura.json
```

### Cliente Python

```python
import requests

# Subir
with open("factura.png", "rb") as f:
    response = requests.post(
        "http://localhost:8000/v1/process",
        files={"file": f}
    )
job_id = response.json()["job_id"]

# Obtener resultados
result = requests.get(f"http://localhost:8000/v1/jobs/{job_id}").json()
print(result["extracted_data"])
```

## Estructura del Proyecto

```
facturaai/
├── src/
│   ├── api/          # Endpoints de FastAPI
│   ├── core/         # Lógica de OCR e IA
│   ├── models/       # Modelos Pydantic
│   └── utils/        # Utilidades
├── tests/            # Archivos de prueba
├── docs/             # Documentación
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## Configuración

| Variable | Descripción | Valor por defecto |
|----------|-------------|-------------------|
| `GROQ_API_KEY` | Clave de API de Groq (requerido) | - |
| `API_HOST` | Host de la API | `0.0.0.0` |
| `API_PORT` | Puerto de la API | `8000` |
| `OCR_LANGUAGES` | Idiomas para OCR | `en,es` |
| `LOG_LEVEL` | Nivel de logging | `INFO` |

## Licencia

Licencia MIT - ver [LICENSE](LICENSE) para más detalles.

## Contribuir

Ver [CONTRIBUTING.md](CONTRIBUTING.md) para las directrices.
