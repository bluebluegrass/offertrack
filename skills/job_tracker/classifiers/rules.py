"""Deterministic rules-first classifier with strong noise filtering."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime

from skills.job_tracker.types import Event, NormalizedMessage

FREE_DOMAINS = {
    "gmail.com",
    "outlook.com",
    "hotmail.com",
    "yahoo.com",
    "icloud.com",
    "proton.me",
    "protonmail.com",
}

ATS_HINTS = {
    "greenhouse.io",
    "ashbyhq.com",
    "lever.co",
    "workday.com",
    "myworkday.com",
    "smartrecruiters.com",
    "jobvite.com",
    "icims.com",
}

INTERVIEW_ANCHOR_PHRASES = [
    "interview",
    "conversation",
    "phone screen",
    "recruiter screen",
    "hiring manager",
]

INTERVIEW_SCHEDULING_PHRASES = [
    "schedule",
    "scheduled",
    "availability",
    "next steps",
    "invite",
    "invitation",
    "confirmation",
    "reschedule",
    "calendar",
]

INTERVIEW_STRONG_PATTERNS = [
    r"schedule (?:your|an?|the)?\s*(?:recruiter\s+screen|phone\s+screen|interview|conversation)",
    r"(?:interview|conversation).{0,24}(?:has been|is|was)?\s*scheduled",
    r"availability(?: request)?.{0,32}(?:interview|conversation)",
    r"(?:interview|conversation) confirmation",
]

INTERVIEW_NEGATIVE_PHRASES = [
    "invoice",
    "receipt",
    "bill",
    "billing",
    "statement",
    "payment",
    "candidate profile",
    "profile purge",
    "profile is about to be purged",
    "order execution",
]

ROLE_PATTERNS = [
    r"for (?:the )?role of ([^\n,|]+)",
    r"for (?:the )?position of ([^\n,|]+)",
    r"position[:\s-]+([^\n|]+)",
    r"application (?:for|to) ([^\n,|]+)",
]

IGNORE_SUBJECT_PREFIX = ("accepted:", "declined:", "tentative:")


@dataclass(slots=True)
class ClassificationDecision:
    events: list[Event]
    ignored: bool
    ignore_reason: str
    application_key: str
    rule_id: str


@dataclass(slots=True)
class ApplicationKeyInfo:
    application_key: str
    key_source: str
    company_domain: str
    company_domain_source: str
    company_name: str
    role_title: str
    role_title_source: str
    role_title_confidence: float


OFFER_PATTERNS = [r"offer letter", r"pleased to offer", r"extend an offer"]

REJECTION_DECISION_PATTERNS = [
    r"decided not to progress your application",
    r"not to progress your application further",
    r"not progress your application further",
    r"will not be progressing your application",
    r"not be taking your application forward",
    r"we have decided not to progress your application further on this occasion",
    r"journey has come to an end",
    r"candidate rejection",
]
REJECTION_CONTEXT_PATTERNS = [r"after careful consideration", r"unfortunately"]
REJECTION_VERB_PATTERNS = [
    r"not moving forward",
    r"regret to inform",
    r"unsuccessful",
    r"position has been filled",
    r"no longer under consideration",
    r"not progress",
    r"not be progressing",
    r"not be taking .* forward",
]
REJECTION_CORE_PATTERNS = REJECTION_DECISION_PATTERNS + [
    r"not moving forward",
    r"regret to inform",
    r"unsuccessful",
    r"position has been filled",
    r"no longer under consideration",
    r"application status",
]

WITHDRAWN_PATTERNS = [r"withdraw(n)? (my )?application", r"withdrawal", r"withdrawn"]
OA_PATTERNS = [r"\boa\b", r"online assessment", r"take-home", r"hackerrank", r"codility", r"assessment"]
ROUND_UPDATE_PATTERNS = [r"round\s*[1-4]", r"final round", r"panel interview"]
STATUS_UPDATE_PATTERNS = [r"application update", r"status update", r"update on your application"]
APPLICATION_RECEIVED_PATTERNS = [
    r"thanks for applying",
    r"thank you for applying",
    r"application received",
    r"application confirmation",
    r"regarding your application",
    r"update on your application",
]


def _norm_text(value: str) -> str:
    out = re.sub(r"[^a-z0-9]+", " ", value.lower())
    return re.sub(r"\s+", " ", out).strip()


def _extract_domain(from_email: str) -> str:
    m = re.search(r"@([A-Za-z0-9_.-]+)", from_email)
    return m.group(1).lower() if m else ""


def _company_name_from_domain(domain: str) -> str:
    if not domain:
        return ""
    parts = domain.split(".")
    if len(parts) < 2:
        return parts[0]
    return parts[-2]


def _extract_company_name_from_text(subject: str, snippet: str) -> str:
    text = f"{subject} | {snippet}"
    patterns = [
        r"\bwith\s+([A-Z][A-Za-z0-9& .'-]{1,64})",
        r"\bat\s+([A-Z][A-Za-z0-9& .'-]{1,64})",
        r"\bjoining\s+([A-Z][A-Za-z0-9& .'-]{1,64})",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            name = re.sub(r"\s+", " ", m.group(1)).strip(" .,-|")
            if name:
                return name.lower()
    return ""


def _extract_company_domain_meta(subject: str, snippet: str, sender_domain: str) -> tuple[str, str]:
    text = f"{subject} {snippet}".lower()
    # Direct domain mention in text is stronger than sender-domain fallback.
    for token in re.findall(r"\b([a-z0-9][a-z0-9.-]+\.[a-z]{2,})\b", text):
        if token in FREE_DOMAINS:
            continue
        return token, "subject_regex"
    if sender_domain and sender_domain not in FREE_DOMAINS:
        if sender_domain in ATS_HINTS or any(h in sender_domain for h in ATS_HINTS):
            return "", "ats_template"
        return sender_domain, "sender_domain"
    return "", "unknown"


def _extract_role_meta(subject: str, snippet: str, domain: str) -> tuple[str, str, float]:
    text = f"{subject} | {snippet}"
    for pattern in ROLE_PATTERNS:
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if m:
            role = _norm_text(m.group(1))
            is_ats_template = ("role of" in text.lower() or "position of" in text.lower() or "position:" in text.lower()) and (
                (domain in ATS_HINTS) or any(h in domain for h in ATS_HINTS)
            )
            conf = 0.9 if is_ats_template else 0.6
            return role, "parsed", conf
    return "", "unknown", 0.0


def get_application_key_info(msg: NormalizedMessage) -> ApplicationKeyInfo:
    sender_domain = _extract_domain(msg.from_email)
    role, role_source, role_conf = _extract_role_meta(msg.subject, msg.snippet, sender_domain)
    extracted_company_domain, company_domain_source = _extract_company_domain_meta(msg.subject, msg.snippet, sender_domain)
    company_name = _company_name_from_domain(extracted_company_domain) if extracted_company_domain else ""
    if not company_name and company_domain_source == "ats_template":
        company_name = _extract_company_name_from_text(msg.subject, msg.snippet)
    if not company_name and sender_domain:
        company_name = _company_name_from_domain(sender_domain)

    # Keep key generation behavior stable: sender domain + role preferred.
    if sender_domain and role and sender_domain not in FREE_DOMAINS:
        return ApplicationKeyInfo(
            application_key=_norm_text(f"{sender_domain} {role}"),
            key_source="domain_role",
            company_domain=extracted_company_domain,
            company_domain_source=company_domain_source,
            company_name=company_name,
            role_title=role,
            role_title_source=role_source,
            role_title_confidence=role_conf,
        )
    if company_name and role:
        return ApplicationKeyInfo(
            application_key=_norm_text(f"{company_name} {role}"),
            key_source="name_role",
            company_domain=extracted_company_domain,
            company_domain_source=company_domain_source,
            company_name=company_name,
            role_title=role,
            role_title_source=role_source,
            role_title_confidence=role_conf,
        )
    if msg.thread_id:
        return ApplicationKeyInfo(
            application_key=_norm_text(msg.thread_id),
            key_source="thread_fallback",
            company_domain=extracted_company_domain,
            company_domain_source=company_domain_source,
            company_name=company_name,
            role_title="",
            role_title_source="unknown",
            role_title_confidence=0.0,
        )
    return ApplicationKeyInfo(
        application_key=_norm_text(msg.id),
        key_source="thread_fallback",
        company_domain=extracted_company_domain,
        company_domain_source=company_domain_source,
        company_name=company_name,
        role_title="",
        role_title_source="unknown",
        role_title_confidence=0.0,
    )


def make_application_key(msg: NormalizedMessage) -> str:
    return get_application_key_info(msg).application_key


def _subject_snippet_hash(subject: str, snippet: str) -> str:
    return hashlib.sha256(f"{subject}|{snippet}".encode("utf-8")).hexdigest()


def _is_calendar_or_survey_noise(msg: NormalizedMessage) -> tuple[bool, str]:
    subject = msg.subject.strip().lower()
    snippet = msg.snippet.lower()
    domain = _extract_domain(msg.from_email)

    if subject.startswith(IGNORE_SUBJECT_PREFIX):
        return True, "calendar_response_prefix"

    if "survey" in subject or "feedback" in subject:
        return True, "survey_feedback_subject"

    if "survey" in domain or "recruitmentsurvey." in domain:
        return True, "survey_domain"

    if domain == "gmail.com" and (
        "accepted:" in subject or "reminder:" in subject or "calendar" in snippet or "invitation" in snippet
    ):
        return True, "gmail_calendar_noise"

    return False, ""


def _should_create_interview_event(msg: NormalizedMessage) -> bool:
    text = f"{msg.subject} {msg.snippet}".lower()
    if any(token in text for token in INTERVIEW_NEGATIVE_PHRASES):
        return False

    if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in INTERVIEW_STRONG_PATTERNS):
        return True

    has_interview_anchor = any(token in text for token in INTERVIEW_ANCHOR_PHRASES)
    if not has_interview_anchor:
        return False

    has_scheduling_signal = any(token in text for token in INTERVIEW_SCHEDULING_PHRASES)
    return has_scheduling_signal


def _match_any(patterns: list[str], text: str) -> str | None:
    for pattern in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            return pattern
    return None


def _is_rejection_text(text: str) -> tuple[bool, str]:
    decision_match = _match_any(REJECTION_DECISION_PATTERNS, text)
    if decision_match:
        return True, f"rejection:decision_phrase:{decision_match}"

    core_match = _match_any(REJECTION_CORE_PATTERNS, text)
    if core_match:
        return True, f"rejection:core_phrases:{core_match}"

    has_context = _match_any(REJECTION_CONTEXT_PATTERNS, text) is not None
    has_decision_verb = _match_any(REJECTION_VERB_PATTERNS, text) is not None
    if has_context and has_decision_verb:
        return True, "rejection:context_plus_decision_verb"

    return False, ""


def _base_evidence(msg: NormalizedMessage, matched_pattern: str, application_key: str) -> dict[str, object]:
    domain = _extract_domain(msg.from_email)
    return {
        "message_id": msg.id,
        "thread_id": msg.thread_id or "",
        "from_domain": domain,
        "subject": msg.subject[:160],
        "subject_snippet_hash": _subject_snippet_hash(msg.subject, msg.snippet),
        "pattern": matched_pattern,
        "ats_sender": (domain in ATS_HINTS) or any(h in domain for h in ATS_HINTS),
        "application_key": application_key,
    }


def normalize_message(raw: dict[str, object]) -> NormalizedMessage:
    occurred = raw.get("date")
    if not isinstance(occurred, datetime):
        occurred = datetime.utcnow()
    return NormalizedMessage(
        id=str(raw.get("id", "")),
        date=occurred,
        from_email=str(raw.get("from_email", "")),
        subject=str(raw.get("subject", "")),
        snippet=str(raw.get("snippet", "")),
        thread_id=(str(raw.get("thread_id", "")) or None),
        body=str(raw.get("body", "")),
    )


def classify_message_with_meta(msg: NormalizedMessage) -> ClassificationDecision:
    application_key = make_application_key(msg)

    ignored, reason = _is_calendar_or_survey_noise(msg)
    if ignored:
        reason_to_rule = {
            "calendar_response_prefix": "ignore:calendar_response_prefix",
            "survey_feedback_subject": "ignore:survey_feedback_subject",
            "survey_domain": "ignore:survey_domain",
            "gmail_calendar_noise": "ignore:gmail_calendar_noise",
        }
        return ClassificationDecision(
            events=[],
            ignored=True,
            ignore_reason=reason,
            application_key=application_key,
            rule_id=reason_to_rule.get(reason, "ignore:unknown"),
        )

    text = f"{msg.subject} {msg.snippet} {msg.from_email}"
    lowered = text.lower()

    # Priority order:
    # offer > rejection > withdrawn > oa > interview_invite/round_update > status_update > application_received > no_match(ignore)
    offer_match = _match_any(OFFER_PATTERNS, text)
    if offer_match:
        ev = Event(
            type="offer",
            stage="Offer",
            occurred_at=msg.date,
            confidence=0.9,
            evidence=_base_evidence(msg, f"offer:core_phrases:{offer_match}", application_key),
            application_key=application_key,
        )
        return ClassificationDecision(events=[ev], ignored=False, ignore_reason="", application_key=application_key, rule_id=f"offer:core_phrases:{offer_match}")

    is_rejection, rejection_rule_id = _is_rejection_text(text)
    if is_rejection:
        ev = Event(
            type="rejection",
            stage="Rejected",
            occurred_at=msg.date,
            confidence=0.95,
            evidence=_base_evidence(msg, rejection_rule_id, application_key),
            application_key=application_key,
        )
        return ClassificationDecision(events=[ev], ignored=False, ignore_reason="", application_key=application_key, rule_id=rejection_rule_id)

    withdrawn_match = _match_any(WITHDRAWN_PATTERNS, text)
    if withdrawn_match:
        ev = Event(
            type="withdrawn",
            stage="Withdrawn",
            occurred_at=msg.date,
            confidence=0.9,
            evidence=_base_evidence(msg, f"withdrawn:core_phrases:{withdrawn_match}", application_key),
            application_key=application_key,
        )
        return ClassificationDecision(events=[ev], ignored=False, ignore_reason="", application_key=application_key, rule_id=f"withdrawn:core_phrases:{withdrawn_match}")

    oa_match = _match_any(OA_PATTERNS, text)
    if oa_match:
        ev = Event(
            type="oa",
            stage="OA",
            occurred_at=msg.date,
            confidence=0.9,
            evidence=_base_evidence(msg, f"oa:core_phrases:{oa_match}", application_key),
            application_key=application_key,
        )
        return ClassificationDecision(events=[ev], ignored=False, ignore_reason="", application_key=application_key, rule_id=f"oa:core_phrases:{oa_match}")

    # Reminder downgrade path: candidate reminder event that may be dropped by pipeline
    if "reminder:" in lowered and ("is on" in lowered or "tomorrow at" in lowered):
        ev = Event(
            type="interview_reminder",
            stage="Interview",
            occurred_at=msg.date,
            confidence=0.4,
            evidence=_base_evidence(msg, "interview_reminder:timing_language", application_key),
            application_key=application_key,
        )
        return ClassificationDecision(
            events=[ev],
            ignored=False,
            ignore_reason="",
            application_key=application_key,
            rule_id="interview_reminder:timing_language",
        )

    if _should_create_interview_event(msg):
        domain = _extract_domain(msg.from_email)
        confidence = 0.9 if (domain and domain not in FREE_DOMAINS) else 0.35
        if domain == "gmail.com":
            # Usually calendar relay/user notifications; ignore unless it has a strong thread key from prior app context.
            return ClassificationDecision(
                events=[],
                ignored=True,
                ignore_reason="gmail_interview_noise",
                application_key=application_key,
                rule_id="ignore:gmail_interview_noise",
            )

        ev = Event(
            type="interview_invite",
            stage="Interview",
            occurred_at=msg.date,
            confidence=confidence,
            evidence=_base_evidence(msg, "interview_invite:schedule_phrases", application_key),
            application_key=application_key,
        )
        return ClassificationDecision(
            events=[ev],
            ignored=False,
            ignore_reason="",
            application_key=application_key,
            rule_id="interview_invite:schedule_phrases",
        )

    round_match = _match_any(ROUND_UPDATE_PATTERNS, text)
    if round_match:
        ev = Event(
            type="round_update",
            stage="Interview",
            occurred_at=msg.date,
            confidence=0.85,
            evidence=_base_evidence(msg, f"round_update:round_phrases:{round_match}", application_key),
            application_key=application_key,
        )
        return ClassificationDecision(events=[ev], ignored=False, ignore_reason="", application_key=application_key, rule_id=f"round_update:round_phrases:{round_match}")

    status_match = _match_any(STATUS_UPDATE_PATTERNS, text)
    if status_match:
        ev = Event(
            type="status_update",
            stage="Applied",
            occurred_at=msg.date,
            confidence=0.7,
            evidence=_base_evidence(msg, f"status_update:core_phrases:{status_match}", application_key),
            application_key=application_key,
        )
        return ClassificationDecision(events=[ev], ignored=False, ignore_reason="", application_key=application_key, rule_id=f"status_update:core_phrases:{status_match}")

    app_received_match = _match_any(APPLICATION_RECEIVED_PATTERNS, text)
    if app_received_match:
        ev = Event(
            type="application_received",
            stage="Applied",
            occurred_at=msg.date,
            confidence=0.9,
            evidence=_base_evidence(msg, f"application_received:core_phrases:{app_received_match}", application_key),
            application_key=application_key,
        )
        return ClassificationDecision(events=[ev], ignored=False, ignore_reason="", application_key=application_key, rule_id=f"application_received:core_phrases:{app_received_match}")

    return ClassificationDecision(
        events=[],
        ignored=True,
        ignore_reason="no_match",
        application_key=application_key,
        rule_id="ignore:no_match",
    )


def classify_message(msg: NormalizedMessage) -> list[Event]:
    return classify_message_with_meta(msg).events
