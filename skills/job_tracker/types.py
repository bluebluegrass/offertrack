"""Public typed contracts for job_tracker."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal, Optional

SourceType = Literal["gmail", "outlook", "sample", "csv"]


@dataclass(slots=True)
class NormalizedMessage:
    id: str
    date: datetime
    from_email: str
    subject: str
    snippet: str
    thread_id: Optional[str] = None
    body: str = ""


@dataclass(slots=True)
class Event:
    type: str
    stage: str
    occurred_at: datetime
    confidence: float
    evidence: dict[str, Any]
    application_key: str


@dataclass(slots=True)
class FunnelMetrics:
    applications: int
    replies: int
    no_replies: int
    oa: int
    withdrawn: int
    interviews: int
    offers: int
    rejected: int


@dataclass(slots=True)
class FunnelRates:
    reply_rate_pct: float
    oa_rate_from_replies_pct: float
    interview_rate_from_oa_pct: float
    offer_rate_from_interviews_pct: float
    rejection_rate_from_interviews_pct: float
    application_to_offer_pct: float


@dataclass(slots=True)
class SkillRunResult:
    run_id: str
    metrics: FunnelMetrics
    rates: FunnelRates
    artifacts: dict[str, str]
    warnings: list[str] = field(default_factory=list)
    debug_samples: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
