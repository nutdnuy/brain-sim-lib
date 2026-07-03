from __future__ import annotations

from pathlib import Path

from brain_sim.models import SimulationSettings


ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DOC = ROOT / "docs" / "brain-settings-and-datafields.md"


def test_settings_reference_doc_exists() -> None:
    assert REFERENCE_DOC.exists()


def test_reference_doc_covers_every_simulation_setting_field() -> None:
    text = REFERENCE_DOC.read_text(encoding="utf-8")

    for field_name in SimulationSettings.__dataclass_fields__:
        assert f"`{field_name}`" in text


def test_reference_doc_maps_ui_labels_from_brain_settings_screenshot() -> None:
    text = REFERENCE_DOC.read_text(encoding="utf-8")

    required_ui_labels = [
        "Language",
        "Instrument Type",
        "Region",
        "Delay",
        "Universe",
        "Neutralization",
        "Decay",
        "Truncation",
        "Pasteurization",
        "Unit Handling",
        "NaN Handling",
        "Test Period",
        "Max Trade",
        "Max Position",
        "Visualization",
    ]
    for label in required_ui_labels:
        assert label in text


def test_reference_doc_covers_data_field_types_and_beginner_rules() -> None:
    text = REFERENCE_DOC.read_text(encoding="utf-8")

    required_terms = [
        "Matrix data field",
        "Vector data field",
        "Group data field",
        "Data Explorer",
        "coverage",
        "cadence",
        "region",
        "delay",
        "vec_avg",
        "group_rank",
        "ts_backfill",
    ]
    for term in required_terms:
        assert term in text
