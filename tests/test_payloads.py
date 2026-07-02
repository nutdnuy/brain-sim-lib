from __future__ import annotations

from brain_sim.models import AlphaExpression, SimulationSettings
from brain_sim.payloads import build_regular_payload, hash_payload, normalize_payload


def test_build_regular_payload_uses_documented_defaults() -> None:
    payload = build_regular_payload(AlphaExpression(row_id="r1", expression="close"))

    assert payload == {
        "type": "REGULAR",
        "settings": {
            "instrumentType": "EQUITY",
            "region": "USA",
            "universe": "TOP3000",
            "delay": 1,
            "decay": 15,
            "neutralization": "SUBINDUSTRY",
            "truncation": 0.08,
            "maxTrade": "ON",
            "pasteurization": "ON",
            "testPeriod": "P1Y6M",
            "unitHandling": "VERIFY",
            "nanHandling": "OFF",
            "language": "FASTEXPR",
            "visualization": False,
        },
        "regular": "close",
    }


def test_hash_payload_is_stable_for_key_order() -> None:
    left = {"type": "REGULAR", "settings": {"region": "USA", "delay": 1}, "regular": "close"}
    right = {"regular": "close", "settings": {"delay": 1, "region": "USA"}, "type": "REGULAR"}

    assert normalize_payload(left) == normalize_payload(right)
    assert hash_payload(left) == hash_payload(right)


def test_expression_specific_settings_override_defaults() -> None:
    expression = AlphaExpression(
        row_id="r2",
        expression="rank(close)",
        settings=SimulationSettings(universe="TOP1000", delay=0, decay=6),
    )

    payload = build_regular_payload(expression)

    assert payload["settings"]["universe"] == "TOP1000"
    assert payload["settings"]["delay"] == 0
    assert payload["settings"]["decay"] == 6
    assert payload["regular"] == "rank(close)"
