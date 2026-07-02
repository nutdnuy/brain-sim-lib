from __future__ import annotations

import hashlib
import json
from typing import Any

from .models import AlphaExpression, PayloadRecord


def build_regular_payload(alpha: AlphaExpression) -> dict[str, Any]:
    return {
        "type": "REGULAR",
        "settings": alpha.settings.to_api_dict(),
        "regular": alpha.expression,
    }


def normalize_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def hash_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(normalize_payload(payload).encode("utf-8")).hexdigest()


def build_payload_record(alpha: AlphaExpression) -> PayloadRecord:
    payload = build_regular_payload(alpha)
    return PayloadRecord(
        row_id=alpha.row_id,
        alpha_hash=hash_payload(payload),
        payload=payload,
        metadata=alpha.metadata,
    )
