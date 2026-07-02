from __future__ import annotations

from brain_sim.cache import SimulationCache


def test_cache_returns_none_for_new_hash(tmp_path) -> None:
    cache = SimulationCache(tmp_path / "cache.sqlite")

    assert cache.lookup("hash-1") is None


def test_cache_reuses_existing_alpha_id(tmp_path) -> None:
    cache = SimulationCache(tmp_path / "cache.sqlite")
    cache.record(alpha_hash="hash-1", alpha_id="abc123", row_id="row-1", status="complete")

    hit = cache.lookup("hash-1")

    assert hit is not None
    assert hit["alpha_id"] == "abc123"
    assert hit["row_id"] == "row-1"
    assert hit["status"] == "complete"


def test_cache_does_not_duplicate_hash_rows(tmp_path) -> None:
    cache = SimulationCache(tmp_path / "cache.sqlite")
    cache.record(alpha_hash="hash-1", alpha_id="first", row_id="row-1", status="complete")
    cache.record(alpha_hash="hash-1", alpha_id="second", row_id="row-2", status="complete")

    assert cache.lookup("hash-1")["alpha_id"] == "second"
    assert len(cache.all_rows()) == 1
