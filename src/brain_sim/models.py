from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class SubmitStatus(str, Enum):
    SKIPPED_DUPLICATE = "skipped_duplicate"
    SUBMITTED = "submitted"
    COMPLETE = "complete"
    PENDING_TIMEOUT = "pending_timeout"
    SUBMIT_ERROR = "submit_error"
    POLL_ERROR = "poll_error"
    EXCEPTION = "exception"


@dataclass(frozen=True)
class SimulationSettings:
    instrumentType: str = "EQUITY"
    region: str = "USA"
    universe: str = "TOP3000"
    delay: int = 1
    decay: int = 15
    neutralization: str = "SUBINDUSTRY"
    truncation: float = 0.08
    maxTrade: str = "ON"
    pasteurization: str = "ON"
    testPeriod: str = "P1Y6M"
    unitHandling: str = "VERIFY"
    nanHandling: str = "OFF"
    language: str = "FASTEXPR"
    visualization: bool = False

    def to_api_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_overrides(cls, overrides: dict[str, Any]) -> "SimulationSettings":
        allowed = set(cls.__dataclass_fields__.keys())
        clean = {key: value for key, value in overrides.items() if key in allowed and value != ""}
        return cls(**clean)


@dataclass(frozen=True)
class AlphaExpression:
    row_id: str
    expression: str
    settings: SimulationSettings = field(default_factory=SimulationSettings)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, init=False)
class PayloadRecord:
    row_id: str
    alpha_hash: str
    _payload: dict[str, Any] = field(repr=False)
    _metadata: dict[str, Any] = field(repr=False)

    def __init__(
        self,
        row_id: str,
        alpha_hash: str,
        payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        object.__setattr__(self, "row_id", row_id)
        object.__setattr__(self, "alpha_hash", alpha_hash)
        object.__setattr__(self, "_payload", deepcopy(payload))
        object.__setattr__(self, "_metadata", deepcopy(metadata or {}))

    @property
    def payload(self) -> dict[str, Any]:
        return deepcopy(self._payload)

    @property
    def metadata(self) -> dict[str, Any]:
        return deepcopy(self._metadata)


@dataclass(frozen=True)
class RateLimitState:
    limit: int | None
    remaining: int | None
    reset_seconds: int | None


@dataclass(frozen=True)
class AuthChallenge:
    url: str
    www_authenticate: str
    message: str
