# Contribuir a FacturaAI

¡Gracias por tu interés en contribuir!

## Configuración del Entorno de Desarrollo

1. Haz un fork del repositorio
2. Clona tu fork: `git clone https://github.com/TU_USUARIO/facturaai.git`
3. Crea una rama de características: `git checkout -b feature/tu-caracteristica`

## Estilo de Código

- Sigue PEP 8
- Usa type hints
- Longitud máxima de línea: 100 caracteres
- Ejecuta el formateo antes de commitear:
  ```bash
  black src/ --line-length 100
  isort src/
  ```

## Pruebas

```bash
# Ejecutar pruebas
pytest tests/ -v

# Ejecutar con cobertura
pytest --cov=src tests/
```

## Mensajes de Commit

Usa commits convencionales:

- `feat: agregar nueva característica`
- `fix: corrección de bug`
- `docs: actualizar documentación`
- `refactor: refactorización de código`
- `test: agregar pruebas`

## Proceso de Pull Request

1. Actualiza la documentación si es necesario
2. Agrega pruebas para nuevas características
3. Asegúrate de que todas las pruebas pasen
4. Actualiza el CHANGELOG si aplica
5. Solicita revisión

## ¿Preguntas?

Abre un issue para preguntas sobre cómo contribuir.
