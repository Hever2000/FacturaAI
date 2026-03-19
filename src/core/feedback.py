import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("factura_ai")

FEEDBACK_DB_PATH = Path("feedback_db.json")
TRAINING_DATA_DIR = Path("training_data")


def get_default_feedback_db() -> dict[str, Any]:
    """Retorna estructura inicial de la base de feedback."""
    return {
        "corrections": [],
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "total_corrections": 0,
        },
    }


def load_feedback_db() -> dict[str, Any]:
    """Carga la base de feedback desde archivo JSON."""
    if not FEEDBACK_DB_PATH.exists():
        return get_default_feedback_db()

    try:
        with open(FEEDBACK_DB_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        logger.error(f"Error loading feedback DB: {e}")
        return get_default_feedback_db()


def save_feedback_db(db: dict[str, Any]) -> None:
    """Guarda la base de feedback a archivo JSON."""
    FEEDBACK_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(FEEDBACK_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)


def add_correction(
    job_id: str,
    field: str,
    wrong_value: Any,
    correct_value: Any,
    raw_text: str,
    extracted_data: dict[str, Any],
) -> dict[str, Any]:
    """
    Agrega una corrección a la base de feedback.

    Args:
        job_id: ID del job procesado
        field: Nombre del campo corregido
        wrong_value: Valor que la IA extrajo incorrectamente
        correct_value: Valor correcto proporcionado por el usuario
        raw_text: Texto OCR original
        extracted_data: Datos extraídos originalmente

    Returns:
        Feedback guardado con metadata
    """
    db = load_feedback_db()

    correction = {
        "id": len(db["corrections"]) + 1,
        "job_id": job_id,
        "field": field,
        "wrong_value": wrong_value,
        "correct_value": correct_value,
        "raw_text": raw_text,
        "extracted_data": extracted_data,
        "timestamp": datetime.now().isoformat(),
    }

    db["corrections"].append(correction)
    db["metadata"]["total_corrections"] = len(db["corrections"])
    db["metadata"]["last_updated"] = datetime.now().isoformat()

    save_feedback_db(db)

    logger.info(f"Correction added: field={field}, job_id={job_id}")

    return correction


def load_feedback_examples(limit: int = 5) -> list[dict[str, Any]]:
    """
    Carga ejemplos de correcciones para usar en few-shot learning.

    Args:
        limit: Número máximo de ejemplos a retornar (más recientes)

    Returns:
        Lista de correcciones recientes
    """
    db = load_feedback_db()
    corrections = db.get("corrections", [])
    return corrections[-limit:] if corrections else []


def generate_training_dataset() -> list[dict[str, Any]]:
    """
    Genera dataset de entrenamiento desde feedback y jobs procesados.

    Cada entrada contiene:
    - text: Texto OCR de la factura
    - response: JSON con datos correctos (considerando correcciones)

    Returns:
        Lista de ejemplos para fine-tuning
    """
    dataset = []

    db = load_feedback_db()
    corrections_by_job = {}

    for correction in db.get("corrections", []):
        job_id = correction["job_id"]
        if job_id not in corrections_by_job:
            corrections_by_job[job_id] = []
        corrections_by_job[job_id].append(correction)

    for _job_id, corrections in corrections_by_job.items():
        job_data = {}
        raw_text = ""

        for corr in corrections:
            if not job_data:
                job_data = corr.get("extracted_data", {}).copy()
                raw_text = corr.get("raw_text", "")

            field = corr["field"]
            if field in job_data:
                job_data[field] = corr["correct_value"]

        if raw_text and job_data:
            dataset.append(
                {
                    "text": raw_text,
                    "response": job_data,
                }
            )

    logger.info(f"Generated training dataset with {len(dataset)} examples")
    return dataset


def export_training_jsonl(filepath: str | None = None) -> str:
    """
    Exporta el dataset de entrenamiento en formato JSONL.

    Args:
        filepath: Ruta opcional. Por defecto: training_data/facturaai_{date}.jsonl

    Returns:
        Ruta del archivo exportado
    """
    TRAINING_DATA_DIR.mkdir(parents=True, exist_ok=True)

    if filepath is None:
        date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = str(TRAINING_DATA_DIR / f"facturaai_{date_str}.jsonl")

    dataset = generate_training_dataset()

    with open(filepath, "w", encoding="utf-8") as f:
        for item in dataset:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    logger.info(f"Training data exported to {filepath}")
    return filepath


def get_feedback_stats() -> dict[str, Any]:
    """Retorna estadísticas del feedback."""
    db = load_feedback_db()

    field_counts: dict[str, int] = {}
    for corr in db.get("corrections", []):
        field = corr["field"]
        field_counts[field] = field_counts.get(field, 0) + 1

    return {
        "total_corrections": db["metadata"]["total_corrections"],
        "field_counts": field_counts,
        "most_corrected_field": max(field_counts, key=field_counts.get) if field_counts else None,
        "last_updated": db["metadata"].get("last_updated"),
    }
