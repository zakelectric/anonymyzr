"""
detector.py
-----------
Local entity detection using GLiNER.

GLiNER is a zero-shot NER model — you define entity labels in plain
English and it finds matching spans in text. No pattern rules needed.

Model is loaded once on first use (~400MB, CPU-compatible).
"""

import os
from typing import List, Dict

import yaml

_config_path = os.path.join(os.path.dirname(__file__), "..", "config", "entity_types.yaml")
with open(_config_path) as f:
    _config = yaml.safe_load(f)

ENTITY_LABELS: List[str] = _config.get("entity_types", [
    "person name", "company name", "address", "email address",
    "phone number", "date of birth", "social security number",
    "credit card number", "bank account number", "dollar amount",
    "ip address", "url", "date",
])

THRESHOLD: float = _config.get("threshold", 0.5)

_model = None


def get_model():
    global _model
    if _model is None:
        from gliner import GLiNER
        print("[anonymyzr] Loading GLiNER model (first run only)...")
        _model = GLiNER.from_pretrained("urchade/gliner_medium-v2.1")
        print("[anonymyzr] GLiNER ready.")
    return _model


def detect_entities(text: str) -> List[Dict]:
    """
    Detect PII entities in text.

    Returns entities sorted by start position DESCENDING so callers
    can safely replace spans right-to-left without position drift.

    Each entity: {"text": str, "label": str, "start": int, "end": int, "score": float}
    """
    if not text or not text.strip():
        return []

    model = get_model()
    raw = model.predict_entities(text, ENTITY_LABELS, threshold=THRESHOLD)

    deduped = _deduplicate(raw)
    deduped.sort(key=lambda e: e["start"], reverse=True)
    return deduped


def _deduplicate(entities: List[Dict]) -> List[Dict]:
    """
    Remove overlapping spans, keeping the highest-confidence entity.
    """
    if not entities:
        return []

    by_score = sorted(entities, key=lambda e: e["score"], reverse=True)
    kept: List[Dict] = []

    for entity in by_score:
        overlaps = any(
            e["start"] < entity["end"] and entity["start"] < e["end"]
            for e in kept
        )
        if not overlaps:
            kept.append(entity)

    return kept
