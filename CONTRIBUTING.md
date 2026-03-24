# Contribuir a FacturaAI

¡Gracias por tu interés en contribuir!

## Configuración del Entorno de Desarrollo

1. Haz un fork del repositorio
2. Clona tu fork: `git clone https://github.com/TU_USUARIO/FacturaAI.git`
3. Entra al directorio: `cd FacturaAI`
4. Crea una rama de características: `git checkout -b feature/tu-caracteristica`

### Requisitos

- Python 3.11+
- PostgreSQL (para desarrollo local)
- Redis (opcional, para cache)

### Instalación

```bash
# Crear entorno virtual
python -m venv venv

# Activar (Linux/Mac)
source venv/bin/activate

# Activar (Windows)
venv\Scripts\activate

# Instalar dependencias
pip install -e .
```

### Variables de Entorno

Crea un archivo `.env` en la raíz del proyecto:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/facturaai

# Redis
REDIS_URL=redis://localhost:6379

# Security
SECRET_KEY=your-secret-key-min-32-chars

# Groq
GROQ_API_KEY=your_groq_api_key

# PaddleOCR-VL
PADDLE_VL_API_URL=https://c6vceb62c4n8zfaf.aistudio-app.com/layout-parsing
PADDLE_VL_TOKEN=your_token

# Mercado Pago
MP_ACCESS_TOKEN=your_mp_access_token
MP_WEBHOOK_SECRET=your_webhook_secret
```

### Ejecutar el Servidor

```bash
uvicorn src.api.main:app --reload --port 8000
```

O con Docker:

```bash
docker-compose up --build
```

## Estilo de Código

- Sigue PEP 8
- Usa type hints
- Longitud máxima de línea: 100 caracteres
- Ejecuta el formateo antes de commitear:

```bash
# Formateo automático
ruff check --fix .
black --line-length=100 .
isort --profile=black .

# Verificación de tipos
mypy src/ --ignore-missing-imports
```

### Convenciones de Nombrado

- **Variables/Funciones**: `snake_case` (ej: `job_id`, `process_ocr`)
- **Clases**: `PascalCase` (ej: `InvoiceData`, `JobStatus`)
- **Constantes**: `UPPER_SNAKE_CASE` (ej: `MAX_FILE_SIZE`)
- **Miembros privados**: Prefijo `_` (ej: `_internal_method`)

### Modelo de Ramas

- `main`: Código en producción (protegido)
- `feature/*`: Nuevas funcionalidades
- `fix/*`: Correcciones de bugs

## Pruebas

```bash
# Ejecutar todas las pruebas
pytest tests/ -v

# Ejecutar con cobertura
pytest --cov=src tests/ --cov-report=html

# Ejecutar prueba específica
pytest tests/test_api.py::test_login
```

## Mensajes de Commit

Usa commits convencionales:

- `feat: agregar nueva característica`
- `fix: corrección de bug`
- `docs: actualizar documentación`
- `refactor: refactorización de código`
- `test: agregar pruebas`
- `chore: tareas de mantenimiento`

## Proceso de Pull Request

1. Actualiza la documentación si es necesario
2. Agrega pruebas para nuevas características
3. Asegúrate de que todas las pruebas pasen
4. Verifica linting y tipos:
   ```bash
   ruff check .
   black --check .
   mypy src/
   ```
5. Solicita revisión

## Reglas de Protección

- ❌ Push directo a `main` PROHIBIDO
- ❌ Commit de secrets/API keys
- ❌ Desactivar CI/CD

## ¿Preguntas?

Abre un issue para preguntas sobre cómo contribuir.
