"""LLM-based email classification and application-table generation."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from collections import Counter, defaultdict
from datetime import datetime
from email.utils import parseaddr
from math import ceil
from pathlib import Path
from time import perf_counter

from app.utils.llm_client import llm_call
from skills.job_tracker.types import NormalizedMessage

CLASSIFICATION_CACHE_VERSION = 2
DEFAULT_CLASSIFICATION_CACHE_PATH = ".cache/job_tracker/llm_classification_cache.json"

ALLOWED_EVENT_TYPES = {"application", "interview", "rejection", "offer", "other"}
SYNTHETIC_EVENT_TYPES = {"irrelevant", "uncertain"}
STATUS_BY_EVENT = {
    "application": "Applied",
    "interview": "Interviewing",
    "rejection": "Rejected",
    "offer": "Offer",
    "other": "Applied",
}
STATUS_PRIORITY = {"Applied": 1, "Interviewing": 2, "Rejected": 3, "Offer": 4}
PERSONAL_EMAIL_ROOTS = {"gmail", "outlook", "hotmail", "yahoo", "icloud", "protonmail"}
INTERMEDIARY_EMAIL_ROOTS = {
    "ashbyhq",
    "codility",
    "codesignal",
    "goodtime",
    "greenhouse",
    "hackerrank",
    "hackerrankforwork",
    "hirevue",
    "icims",
    "jobvite",
    "lever",
    "myworkday",
    "recruitee",
    "smartrecruiters",
    "teamtailor",
    "workday",
}
GENERIC_SENDER_TOKENS = {
    "at",
    "career",
    "careers",
    "email",
    "hiring",
    "hr",
    "jobs",
    "no",
    "notifications",
    "noreply",
    "recruiting",
    "recruitment",
    "reply",
    "support",
    "talent",
    "team",
    "the",
    "via",
}
COMPANYISH_TOKENS = {
    "ai",
    "analytics",
    "data",
    "digital",
    "group",
    "labs",
    "media",
    "people",
    "solutions",
    "studio",
    "systems",
    "team",
    "tech",
    "technologies",
}
CALENDAR_RSVP_PREFIXES = ("accepted:", "tentative accepted:", "declined:")
DOMAIN_PREFIX_CANDIDATES = ("team", "get", "my", "go")
INTERVIEW_ANCHOR_TERMS = (
    "interview",
    "phone screen",
    "technical screen",
    "recruiter screen",
    "onsite",
    "final round",
)
INTERVIEW_INVITE_TERMS = (
    "invitation",
    "meeting invite",
    "calendar invite",
    "invite accepted",
    "google calendar",
    "outlook calendar",
    "meet google com",
    "teams microsoft com",
    "zoom us",
    "webex",
    "ics",
)
INTERVIEW_SCHEDULED_TERMS = (
    "has been scheduled",
    "is scheduled",
    "was scheduled",
    "scheduled for",
    "rescheduled",
    "interview confirmation",
    "your interview is on",
    "your interview has been scheduled",
)
INTERVIEW_WEAK_FUTURE_TERMS = (
    "we will schedule",
    "we'll schedule",
    "we would like to schedule",
    "we may schedule",
    "if there is strong alignment",
)
NON_EMPLOYER_TOOL_ROOTS = {"tealhq"}
NON_EMPLOYER_TOOL_MARKETING_TERMS = (
    "ai interview prep",
    "practice interview",
    "practice interviews",
    "teal job tracker",
    "instant feedback",
    "target roles",
    "build confidence",
    "track the status of every job application",
    "stay on top of every opportunity",
    "keep every opportunity organized",
    "clear visibility into next steps and follow ups",
    "missed connections",
)
NON_EMPLOYER_LOGISTICS_ROOTS = {"sirva"}
NON_EMPLOYER_LOGISTICS_TERMS = (
    "expense report",
    "candidate per diem",
    "per diem",
    "amount approved",
    "funds have been issued",
    "audited by sirva",
)
REJECTION_SIGNAL_PATTERNS = (
    r"regret to inform",
    r"not moving forward",
    r"not be moving forward",
    r"won t be moving forward",
    r"not progress your application",
    r"not progressing your application",
    r"not be taking your application forward",
    r"won'?t be able to proceed further",
    r"will not be able to proceed further",
    r"no longer under consideration",
    r"position has been filled",
    r"filled the position",
    r"filled the role",
    r"move forward with another candidate",
    r"moving forward with another candidate",
    r"selected another candidate",
    r"application has come to an end",
    r"journey has come to an end",
    r"candidate rejection",
    r"after careful consideration.{0,80}unfortunately",
)
LLM_CONCURRENCY_CAP = 4
# Executor wait cap for each submitted classification future. This is distinct
# from the HTTP/network timeout passed down to `llm_call`.
CALL_TIMEOUT_S = 12.0
PREFILTER_KEYWORDS = (
    "interview",
    "offer",
    "application",
    "applied",
    "thank you for applying",
    "received your",
    "your submission",
    "position",
    "role",
    "opportunity",
    "recruiter",
    "hiring",
    "assessment",
    "shortlist",
    "profile",
    "rejection",
    "rejected",
    "unfortunately",
    "next steps",
    "we will be in touch",
    "we ll be in touch",
    "get back to you",
    "move forward",
    "decision",
    "candidate",
)
PREFILTER_DOMAIN_PATTERNS = (
    "greenhouse",
    "lever",
    "workday",
    "myworkdayjobs",
    "ashbyhq",
    "linkedin",
    "indeed",
    "smartrecruiters",
    "icims",
    "jobvite",
    "recruitee",
    "teamtailor",
    "greenhouse-mail",
    "teamtailor-mail",
    "goodtime",
    "hirevue",
    "hackerrank",
    "hackerrankforwork",
    "codesignal",
    "modernloop",
    "appreview.gem",
)


def _normalize_text(value: str) -> str:
    out = re.sub(r"[^a-z0-9]+", " ", (value or "").lower())
    return re.sub(r"\s+", " ", out).strip()


def _sender_email_address(raw_from: str) -> str:
    _, addr = parseaddr(raw_from or "")
    return addr.strip().lower()


def _sender_domain(addr: str) -> str:
    if "@" not in addr:
        return ""
    return addr.split("@", 1)[1].strip().lower()


def _domain_root_from_email(addr: str) -> str:
    if "@" not in addr:
        return ""
    domain = addr.split("@", 1)[1].strip().lower()
    parts = domain.split(".")
    if len(parts) < 2:
        return ""
    return parts[-2]


def _tokenize(text: str) -> set[str]:
    return {t for t in _normalize_text(text).split() if t}


def _prefilter_has_keyword(text: str) -> bool:
    lowered = (text or "").lower()
    return any(keyword in lowered for keyword in PREFILTER_KEYWORDS)


def _prefilter_domain_match(sender_addr: str) -> bool:
    domain = _sender_domain(sender_addr)
    if not domain:
        return False
    return any(pattern in domain for pattern in PREFILTER_DOMAIN_PATTERNS)


def _message_value(message: dict[str, object] | NormalizedMessage, field: str) -> object:
    if isinstance(message, dict):
        return message.get(field)
    return getattr(message, field)


def prefilter_candidates(
    messages: list[dict[str, object]] | list[NormalizedMessage],
) -> tuple[list[dict[str, object] | NormalizedMessage], list[dict[str, object] | NormalizedMessage]]:
    to_classify: list[dict[str, object] | NormalizedMessage] = []
    skipped: list[dict[str, object] | NormalizedMessage] = []
    for message in messages:
        sender_addr = _sender_email_address(str(_message_value(message, "from_email") or ""))
        subject = str(_message_value(message, "subject") or "")
        snippet = str(_message_value(message, "snippet") or "")
        body = str(_message_value(message, "body") or "")

        domain_match = _prefilter_domain_match(sender_addr)
        subject_match = _prefilter_has_keyword(subject)
        body_match = _prefilter_has_keyword(" ".join(part for part in [snippet, body] if part))

        if (not domain_match) and (not subject_match) and (not body_match):
            skipped.append(message)
        else:
            to_classify.append(message)
    return to_classify, skipped


def _company_from_domain_root(root: str, context_text: str = "") -> str:
    root_norm = _normalize_text(root)
    if not root_norm:
        return ""
    if root_norm in PERSONAL_EMAIL_ROOTS or root_norm in INTERMEDIARY_EMAIL_ROOTS:
        return ""

    context_norm = _normalize_text(context_text)
    candidates: list[str] = []
    for prefix in DOMAIN_PREFIX_CANDIDATES:
        if not root_norm.startswith(prefix):
            continue
        stripped = root_norm[len(prefix):].strip()
        if len(stripped) < 3:
            continue
        if context_norm and re.search(rf"\b{re.escape(stripped)}\b", context_norm):
            candidates.append(stripped)
    candidates.append(root_norm)
    return min(candidates, key=len)


def _company_from_sender_domain(sender_addr: str, context_text: str = "") -> str:
    return _company_from_domain_root(_domain_root_from_email(sender_addr), context_text)


def _strip_company_suffixes(value: str) -> str:
    c = _normalize_text(value)
    suffixes = [" inc", " llc", " ltd", " bv", " gmbh", " corp", " company", " group", " co"]
    changed = True
    while changed and c:
        changed = False
        for suffix in suffixes:
            if c.endswith(suffix):
                c = c[: -len(suffix)].strip()
                changed = True
                break
    if c.endswith(" com"):
        c = c[:-4].strip()
    if c.endswith(" io"):
        c = c[:-3].strip()
    if c.endswith(" co uk"):
        c = c[:-6].strip()
    return c


def _sender_display_name(raw_from: str) -> str:
    name, _ = parseaddr(raw_from or "")
    return name.strip()


def _company_from_sender_display(raw_from: str) -> str:
    raw_display = _sender_display_name(raw_from)
    if not raw_display:
        return ""
    for separator in ("/", "|", " - ", ":", "(", "@"):
        if separator in raw_display:
            raw_display = raw_display.split(separator, 1)[0].strip()
    display = _normalize_text(raw_display)
    if " via " in display:
        display = display.split(" via ", 1)[0].strip()
    if not display:
        return ""
    tokens = [t for t in display.split() if t not in GENERIC_SENDER_TOKENS]
    if not tokens:
        return ""
    return _strip_company_suffixes(" ".join(tokens))


def _company_from_text(text: str) -> str:
    raw_text = text or ""
    roots: list[str] = []
    for match in re.finditer(r"\b([a-z0-9-]+)\.(?:com|co|io|ai|net|org|eu|nl)\b", raw_text.lower()):
        hint = _company_from_domain_root(match.group(1), raw_text)
        if hint:
            roots.append(hint)
    if roots:
        return Counter(roots).most_common(1)[0][0]
    plain_patterns = [
        r"\b([A-Z][A-Za-z0-9& .'-]{1,64}?)\s+\|\s+update on your application\b",
        r"\bthank you for applying to\s+([A-Z][A-Za-z0-9& .'-]{1,64}?)(?=$|[,.!?:]|\s{2,}|\n)",
        r"\bapplication with\s+([A-Z][A-Za-z0-9& .'-]{1,64}?)(?=$|[,.!?:]|\s{2,}|\n)",
        r"\bposition at\s+([A-Z][A-Za-z0-9& .'-]{1,64}?)(?=$|[,.!?:]|\s{2,}|\n)",
        r"\bupdate with\s+([A-Z][A-Za-z0-9& .'-]{1,64}?)(?=\s+-|$|[,.!?:]|\s{2,}|\n)",
        r"\binterest in\s+([A-Z][A-Za-z0-9& .'-]{1,64}?)(?=$|[,.!?:]|\s{2,}|\n)",
        r"\bwith us at\s+([A-Z][A-Za-z0-9& .'-]{1,64}?)(?=$|[,.!?:]|\s{2,}|\n)",
        r"\bfrom\s+([A-Z][A-Za-z0-9& .'-]{1,64}?)(?=$|[,.!?:]|\s{2,}|\n)",
        r"\bupdate\s+([A-Z][A-Za-z0-9& .'-]{1,64}?)\s+application\b",
    ]
    for pattern in plain_patterns:
        match = re.search(pattern, raw_text, flags=re.IGNORECASE)
        if match:
            return _strip_company_suffixes(match.group(1))
    return ""


def _looks_like_person_name(value: str) -> bool:
    tokens = [t for t in _normalize_text(value).split() if t]
    if len(tokens) < 2:
        return False
    if any(token in COMPANYISH_TOKENS for token in tokens):
        return False
    if not tokens[0].isalpha() or len(tokens[0]) <= 1:
        return False
    return all(token.isalpha() and len(token) >= 1 for token in tokens[1:])


def _looks_like_intermediary_label(value: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "", _normalize_text(value))
    if not normalized:
        return False
    for root in INTERMEDIARY_EMAIL_ROOTS:
        root_norm = re.sub(r"[^a-z0-9]+", "", root)
        if normalized == root_norm or normalized.startswith(root_norm) or root_norm.startswith(normalized):
            return True
    return False


def _has_valid_company_label(value: str) -> bool:
    normalized = _strip_company_suffixes(value)
    if not normalized:
        return False
    if normalized in PERSONAL_EMAIL_ROOTS or normalized in INTERMEDIARY_EMAIL_ROOTS:
        return False
    if _looks_like_person_name(normalized) or _looks_like_intermediary_label(normalized):
        return False
    return True


def _is_calendar_rsvp_noise(sender_addr: str, subject: str) -> bool:
    root = _domain_root_from_email(sender_addr)
    subj = (subject or "").strip().lower()
    if root not in PERSONAL_EMAIL_ROOTS:
        return False
    if not subj.startswith(CALENDAR_RSVP_PREFIXES):
        return False
    return "interview" in subj


def _has_meeting_invite_signal(subject: str, body: str = "") -> bool:
    raw_text = " ".join([subject or "", body or ""]).lower()
    text = _normalize_text(raw_text)
    if not text:
        return False

    has_invite = any(term in text for term in INTERVIEW_INVITE_TERMS)
    has_anchor = any(term in text for term in INTERVIEW_ANCHOR_TERMS)
    has_scheduled = any(term in text for term in INTERVIEW_SCHEDULED_TERMS)
    weak_future_only = any(term in text for term in INTERVIEW_WEAK_FUTURE_TERMS)

    # Calendar/invite language with interview terms is a strong signal.
    if has_invite and (has_anchor or "call" in text or "meeting" in text):
        return True
    # Explicitly scheduled interview language is a strong signal.
    if has_anchor and has_scheduled:
        return True
    # Invitation subject lines ("Invitation: ... @ ...") should count.
    if "invitation" in text and "@" in raw_text and (has_anchor or "call" in text or "meeting" in text):
        return True

    # "We may schedule a call later" should not count as interview.
    if weak_future_only:
        return False
    return False


def _effective_event_type(row: dict[str, str]) -> str:
    event_type = (row.get("event_type", "") or "").strip().lower()
    if event_type != "interview":
        return event_type
    meeting_signal = (row.get("meeting_signal", "") or "").strip().lower()
    if meeting_signal in {"true", "1", "yes"}:
        return "interview"
    if meeting_signal in {"false", "0", "no"}:
        return "other"
    if _has_meeting_invite_signal(row.get("subject", ""), row.get("body", "")):
        return "interview"
    return "other"


def _counts_as_application_event(row: dict[str, str]) -> bool:
    return _effective_event_type(row) in {"application", "interview", "rejection", "offer"}


def _has_rejection_signal(subject: str, body: str = "") -> bool:
    text = _normalize_text(" ".join([subject or "", body or ""]))
    if not text:
        return False
    if "unsuccessful" in text and (
        "application" in text or "candidacy" in text or "role" in text or "position" in text
    ):
        return True
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in REJECTION_SIGNAL_PATTERNS)


def _is_non_employer_tool_email(sender_addr: str, subject: str, body: str = "", company: str = "") -> bool:
    root = _domain_root_from_email(sender_addr)
    if root not in NON_EMPLOYER_TOOL_ROOTS:
        return False
    text = _normalize_text(" ".join([subject or "", body or "", company or ""]))
    return any(term in text for term in NON_EMPLOYER_TOOL_MARKETING_TERMS)


def _is_non_employer_logistics_email(sender_addr: str, subject: str, body: str = "", company: str = "") -> bool:
    root = _domain_root_from_email(sender_addr)
    if root not in NON_EMPLOYER_LOGISTICS_ROOTS:
        return False
    text = _normalize_text(" ".join([subject or "", body or "", company or ""]))
    return any(term in text for term in NON_EMPLOYER_LOGISTICS_TERMS)


def _canonical_company_name(
    raw_company: str,
    sender_addr: str,
    *,
    sender_raw: str = "",
    subject: str = "",
    body: str = "",
) -> str:
    c = _strip_company_suffixes(raw_company)
    root = _domain_root_from_email(sender_addr)
    message_text = "\n".join(part for part in [subject or "", body or ""] if part)
    context_text = " ".join([sender_raw or "", message_text, c or ""])
    sender_domain_hint = _company_from_sender_domain(sender_addr, context_text)
    text_hint = _company_from_text(message_text) or _company_from_text(context_text)
    display_hint = _company_from_sender_display(sender_raw)
    valid_c = _has_valid_company_label(c)

    if root in PERSONAL_EMAIL_ROOTS:
        if valid_c:
            return c
        if text_hint:
            return text_hint
        if display_hint and not _looks_like_person_name(display_hint):
            return display_hint

    if root in INTERMEDIARY_EMAIL_ROOTS or _looks_like_intermediary_label(c):
        if display_hint and c and c.startswith(f"{display_hint} "):
            return display_hint
        if valid_c:
            return c
        if text_hint:
            return text_hint
        if display_hint and not _looks_like_person_name(display_hint) and not _looks_like_intermediary_label(display_hint):
            return display_hint
        if sender_domain_hint:
            return sender_domain_hint

    if valid_c:
        c_tokens = _tokenize(c)
        if sender_domain_hint and (
            sender_domain_hint in c or c in sender_domain_hint or bool(c_tokens & _tokenize(sender_domain_hint))
        ):
            return sender_domain_hint
        if text_hint and (text_hint in c or c in text_hint or bool(c_tokens & _tokenize(text_hint))):
            return text_hint
        return c

    if text_hint:
        return text_hint

    if sender_domain_hint:
        return sender_domain_hint

    if root in INTERMEDIARY_EMAIL_ROOTS:
        if display_hint and display_hint not in INTERMEDIARY_EMAIL_ROOTS:
            return display_hint

    if not c and root:
        c = _normalize_text(root)
    return c


def _similar_company_labels(a: str, b: str) -> bool:
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    return bool(_tokenize(a) & _tokenize(b))


def _row_company_label(row: dict[str, str]) -> str:
    return _canonical_company_name(
        row.get("company", ""),
        row.get("from_email_address", ""),
        sender_raw=row.get("from_email_raw", ""),
        subject=row.get("subject", ""),
    )


def _build_domain_alias_map(message_rows: list[dict[str, str]]) -> dict[tuple[str, str], str]:
    domain_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for r in message_rows:
        if r.get("is_job_related") != "true":
            continue
        sender = r.get("from_email_address", "")
        if _is_calendar_rsvp_noise(sender, r.get("subject", "")):
            continue
        root = _domain_root_from_email(sender)
        if not root or root in PERSONAL_EMAIL_ROOTS or root in INTERMEDIARY_EMAIL_ROOTS:
            continue
        label = _row_company_label(r)
        if label:
            domain_counts[root][label] += 1

    alias_map: dict[tuple[str, str], str] = {}
    for root, counts in domain_counts.items():
        labels = list(counts.keys())
        if len(labels) < 2:
            continue
        scores = {
            lbl: (
                sum(counts[other] for other in labels if _similar_company_labels(lbl, other)),
                counts[lbl],
                -len(lbl),
            )
            for lbl in labels
        }
        target = max(labels, key=lambda lbl: scores[lbl])
        for lbl in labels:
            if lbl == target:
                continue
            if _similar_company_labels(lbl, target):
                alias_map[(root, lbl)] = target
    return alias_map


def _resolved_row_company(row: dict[str, str], alias_map: dict[tuple[str, str], str]) -> str:
    label = _row_company_label(row)
    sender = row.get("from_email_address", "")
    root = _domain_root_from_email(sender)
    if root and label:
        return alias_map.get((root, label), label)
    return label


def _require_api_key(env_var: str) -> str:
    key = os.environ.get(env_var, "").strip()
    if not key:
        raise ValueError(f"Missing API key in environment variable: {env_var}")
    return key


def _extract_json_object(text: str) -> dict[str, object]:
    s = text.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", s)
        s = re.sub(r"\n?```$", "", s)
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", s, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _extract_llm_text(data: dict[str, object]) -> str:
    """Support both Responses API output and legacy chat-completions shape."""
    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    output = data.get("output")
    if isinstance(output, list):
        chunks: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict):
                    continue
                text = part.get("text")
                if isinstance(text, str):
                    chunks.append(text)
        if chunks:
            return "\n".join(chunks)

    return (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )


def _build_llm_request(
    *,
    message: NormalizedMessage,
    model: str,
    max_body_chars: int,
) -> tuple[str, dict[str, object]]:
    sender_address = _sender_email_address(message.from_email)
    payload = {
        "sender_email": sender_address,
        "subject": message.subject,
        "body": (message.body or message.snippet)[:max_body_chars],
        "received_at": message.date.isoformat(),
    }
    system_prompt = (
        "You classify job-search emails. "
        "Return only a JSON object with keys: "
        "is_job_related (boolean), company (string), position (string), "
        "event_type (application|interview|rejection|offer|other), confidence (number 0..1). "
        "For company, use the base brand name and drop org/legal suffixes such as group/inc/llc/ltd. "
        "Count interview only when there is an explicit meeting invite/scheduled interview signal. "
        "If not job-related, set is_job_related=false and event_type=other."
    )
    user_prompt = "Classify this email:\n" + json.dumps(payload, ensure_ascii=True)
    body = {
        "model": model,
        "temperature": 0,
        "text": {"format": {"type": "json_object"}},
        "input": [
            {"role": "system", "content": [{"type": "input_text", "text": system_prompt}]},
            {"role": "user", "content": [{"type": "input_text", "text": user_prompt}]},
        ],
    }
    return sender_address, body


def _llm_request_cache_key(body: dict[str, object]) -> str:
    serialized = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _parse_llm_classification(
    *,
    message: NormalizedMessage,
    sender_address: str,
    data: dict[str, object],
) -> dict[str, object]:
    content = _extract_llm_text(data)
    parsed = _extract_json_object(content)
    event_type = str(parsed.get("event_type", "other")).strip().lower()
    if event_type not in ALLOWED_EVENT_TYPES:
        event_type = "other"

    raw_conf = parsed.get("confidence", 0.0)
    try:
        conf = float(raw_conf)
    except (TypeError, ValueError):
        conf = 0.0
    conf = max(0.0, min(1.0, conf))

    is_job_related = bool(parsed.get("is_job_related", False))
    company = _canonical_company_name(
        str(parsed.get("company", "")),
        sender_address,
        sender_raw=message.from_email,
        subject=message.subject,
        body=message.body or message.snippet,
    )
    meeting_signal = _has_meeting_invite_signal(message.subject, message.body or message.snippet)
    if _is_calendar_rsvp_noise(sender_address, message.subject):
        is_job_related = False
        event_type = "other"
        company = ""
    elif _is_non_employer_tool_email(sender_address, message.subject, message.body or message.snippet, company):
        is_job_related = False
        event_type = "other"
        company = ""
    elif _is_non_employer_logistics_email(sender_address, message.subject, message.body or message.snippet, company):
        is_job_related = False
        event_type = "other"
        company = ""
    elif _has_rejection_signal(message.subject, message.body or message.snippet):
        is_job_related = True
        event_type = "rejection"
    elif event_type == "interview" and not meeting_signal:
        event_type = "other"

    return {
        "is_job_related": is_job_related,
        "company": company,
        "position": _normalize_text(str(parsed.get("position", ""))),
        "event_type": event_type,
        "confidence": conf,
        "meeting_signal": meeting_signal,
    }


def _build_classification_row(
    *,
    message: NormalizedMessage,
    sender_address: str,
    classification: dict[str, object],
) -> dict[str, object]:
    event_type = str(classification.get("event_type", "other"))
    return {
        "gmail_message_id": message.id,
        "thread_id": message.thread_id or "",
        "date": message.date.isoformat(),
        "from_email_raw": message.from_email,
        "from_email_address": sender_address,
        "subject": message.subject[:200],
        "is_job_related": "true" if bool(classification.get("is_job_related", False)) else "false",
        "company": str(classification.get("company", "")),
        "position": str(classification.get("position", "")),
        "event_type": event_type,
        "status": STATUS_BY_EVENT.get(event_type, "Applied"),
        "confidence": f"{float(classification.get('confidence', 0.0)):.2f}",
        "meeting_signal": "true" if bool(classification.get("meeting_signal", False)) else "false",
    }


def _deterministic_rejection_classification(message: NormalizedMessage, sender_address: str) -> dict[str, object]:
    sender_display_company = _company_from_sender_display(message.from_email)
    return {
        "is_job_related": True,
        "company": _canonical_company_name(
            sender_display_company,
            sender_address,
            sender_raw=message.from_email,
            subject=message.subject,
            body=message.body or message.snippet,
        ),
        "position": "",
        "event_type": "rejection",
        "confidence": 1.0,
        "meeting_signal": False,
    }


def _llm_classify_single_email(
    *,
    message: NormalizedMessage,
    model: str,
    api_key: str,
    base_url: str,
    max_body_chars: int,
    timeout_sec: int,
) -> tuple[dict[str, object], float, int]:
    sender_address, body = _build_llm_request(
        message=message,
        model=model,
        max_body_chars=max_body_chars,
    )

    started_at = perf_counter()
    try:
        data = llm_call(
            "gmail_classification",
            api_key=api_key,
            base_url=base_url,
            timeout_sec=timeout_sec,
            **body,
        )
    except RuntimeError as exc:
        raise RuntimeError(str(exc)) from exc
    elapsed = perf_counter() - started_at
    token_total = 0
    usage = data.get("usage")
    if isinstance(usage, dict):
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        if isinstance(input_tokens, int) and isinstance(output_tokens, int):
            token_total = input_tokens + output_tokens

    classification = _parse_llm_classification(
        message=message,
        sender_address=sender_address,
        data=data,
    )
    return (classification, elapsed, token_total)


def _prefilter_skipped_row(message: NormalizedMessage) -> dict[str, str]:
    sender_address = _sender_email_address(message.from_email)
    return {
        "gmail_message_id": message.id,
        "thread_id": message.thread_id or "",
        "date": message.date.isoformat(),
        "from_email_raw": message.from_email,
        "from_email_address": sender_address,
        "subject": message.subject[:200],
        "is_job_related": "false",
        "company": "",
        "position": "",
        "event_type": "irrelevant",
        "status": "",
        "confidence": "0.00",
        "meeting_signal": "false",
    }


def _timed_out_uncertain_row(message: NormalizedMessage) -> dict[str, str]:
    sender_address = _sender_email_address(message.from_email)
    return {
        "gmail_message_id": message.id,
        "thread_id": message.thread_id or "",
        "date": message.date.isoformat(),
        "from_email_raw": message.from_email,
        "from_email_address": sender_address,
        "subject": message.subject[:200],
        "is_job_related": "unknown",
        "company": "",
        "position": "",
        "event_type": "uncertain",
        "status": "",
        "confidence": "0.00",
        "meeting_signal": "false",
    }


def _init_timing_defaults(timing: dict[str, object], *, candidate_count: int = 0, skipped_count: int = 0) -> None:
    timing["candidate_count"] = candidate_count
    timing["skipped_by_prefilter"] = skipped_count
    timing["llm_concurrency_cap"] = LLM_CONCURRENCY_CAP
    timing.setdefault("llm_cache_hits", 0)
    timing.setdefault("llm_cache_misses", 0)
    timing.setdefault("llm_classify_total_time_s", 0.0)
    timing.setdefault("llm_calls_count", 0)
    timing.setdefault("fallback_count", 0)
    timing.setdefault("token_usage_total", 0)
    timing.setdefault("timeout_count", 0)
    timing.setdefault("timeout_retry_exhausted_count", 0)
    timing.setdefault("_llm_call_durations_s", [])


def _record_llm_attempt_submitted(timing: dict[str, object] | None) -> None:
    if timing is None:
        return
    timing["llm_calls_count"] = int(timing.get("llm_calls_count", 0)) + 1


def _record_llm_cache_hit(timing: dict[str, object] | None) -> None:
    if timing is None:
        return
    timing["llm_cache_hits"] = int(timing.get("llm_cache_hits", 0)) + 1


def _record_llm_cache_miss(timing: dict[str, object] | None) -> None:
    if timing is None:
        return
    timing["llm_cache_misses"] = int(timing.get("llm_cache_misses", 0)) + 1


def _record_llm_attempt_observed(timing: dict[str, object] | None, *, elapsed: float, token_total: int) -> None:
    if timing is None:
        return
    durations = timing.setdefault("_llm_call_durations_s", [])
    if isinstance(durations, list):
        durations.append(elapsed)
    timing["token_usage_total"] = int(timing.get("token_usage_total", 0)) + token_total


def _record_llm_timeout_observed(timing: dict[str, object] | None) -> None:
    if timing is None:
        return
    durations = timing.setdefault("_llm_call_durations_s", [])
    if isinstance(durations, list):
        durations.append(CALL_TIMEOUT_S)


def _finalize_llm_timing(timing: dict[str, object] | None, *, classify_elapsed: float) -> None:
    if timing is None:
        return
    timing["llm_classify_total_time_s"] = classify_elapsed
    calls = int(timing.get("llm_calls_count", 0))
    total = float(timing.get("llm_classify_total_time_s", 0.0))
    timing["llm_avg_time_per_call_s"] = (total / calls) if calls else 0.0
    # Durations are "observed attempt durations":
    # - successful attempts record their full underlying runtime
    # - timed-out attempts record CALL_TIMEOUT_S
    # Because futures are submitted before they are awaited, a successful call can
    # legitimately exceed CALL_TIMEOUT_S if most of its runtime elapsed before
    # future.result(timeout=...) was observed. So llm_max_time_s > CALL_TIMEOUT_S
    # is expected and does not by itself mean timeout enforcement is broken.
    durations = sorted(float(v) for v in timing.get("_llm_call_durations_s", []) if isinstance(v, (int, float)))
    if durations:
        midpoint = len(durations) // 2
        if len(durations) % 2 == 1:
            p50 = durations[midpoint]
        else:
            p50 = (durations[midpoint - 1] + durations[midpoint]) / 2.0
        p95_index = max(0, ceil(len(durations) * 0.95) - 1)
        timing["llm_p50_time_s"] = p50
        timing["llm_p95_time_s"] = durations[p95_index]
        timing["llm_max_time_s"] = durations[-1]
    else:
        timing["llm_p50_time_s"] = 0.0
        timing["llm_p95_time_s"] = 0.0
        timing["llm_max_time_s"] = 0.0


def _load_classification_cache(cache_path: str | None) -> dict[str, dict[str, object]]:
    # Cache stores only successful semantic classification payloads keyed by the
    # exact serialized LLM request body. Any missing/corrupt/incompatible file is
    # treated as a cold cache so we never fail closed or reuse ambiguous data.
    if not cache_path:
        return {}
    path = Path(cache_path).expanduser().resolve()
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    if int(payload.get("version", 0)) != CLASSIFICATION_CACHE_VERSION:
        return {}
    entries = payload.get("entries")
    if not isinstance(entries, dict):
        return {}
    out: dict[str, dict[str, object]] = {}
    for key, value in entries.items():
        if isinstance(key, str) and isinstance(value, dict):
            out[key] = value
    return out


def _save_classification_cache(cache_path: str | None, entries: dict[str, dict[str, object]]) -> None:
    if not cache_path:
        return
    path = Path(cache_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    # Only successful classifications are written here. Timeout-exhausted
    # "uncertain" rows are intentionally excluded from the cache because they
    # represent transient API failures, not trustworthy semantic results.
    payload = {
        "version": CLASSIFICATION_CACHE_VERSION,
        "entries": entries,
    }
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    tmp_path.replace(path)


def _submit_cached_classification_task(
    *,
    executor: ThreadPoolExecutor,
    pending_by_key: dict[str, dict[str, object]],
    completed_by_key: dict[str, dict[str, object]],
    message: NormalizedMessage,
    model: str,
    api_key: str,
    base_url: str,
    max_body_chars: int,
    timeout_sec: int,
    timing: dict[str, object] | None,
) -> tuple[str, str, dict[str, object] | None]:
    sender_address, request_body = _build_llm_request(
        message=message,
        model=model,
        max_body_chars=max_body_chars,
    )
    cache_key = _llm_request_cache_key(request_body)
    cached = completed_by_key.get(cache_key)
    if cached is not None:
        _record_llm_cache_hit(timing)
        return cache_key, sender_address, cached
    if cache_key in pending_by_key:
        _record_llm_cache_hit(timing)
        return cache_key, sender_address, None

    if _has_rejection_signal(message.subject, message.body or message.snippet):
        _record_llm_cache_miss(timing)
        classification = _deterministic_rejection_classification(message, sender_address)
        completed_by_key[cache_key] = classification
        return cache_key, sender_address, classification

    _record_llm_cache_miss(timing)
    _record_llm_attempt_submitted(timing)
    future = executor.submit(
        _llm_classify_single_email,
        message=message,
        model=model,
        api_key=api_key,
        base_url=base_url,
        max_body_chars=max_body_chars,
        timeout_sec=timeout_sec,
    )
    pending_by_key[cache_key] = {
        "future": future,
        "message": message,
        "sender_address": sender_address,
    }
    return cache_key, sender_address, None


def _resolve_pending_cached_classification(
    *,
    executor: ThreadPoolExecutor,
    cache_key: str,
    sender_address: str,
    pending_by_key: dict[str, dict[str, object]],
    completed_by_key: dict[str, dict[str, object]],
    message: NormalizedMessage,
    model: str,
    api_key: str,
    base_url: str,
    max_body_chars: int,
    timeout_sec: int,
    timing: dict[str, object] | None,
) -> dict[str, str]:
    cached = completed_by_key.get(cache_key)
    if cached is not None:
        return _build_classification_row(message=message, sender_address=sender_address, classification=cached)

    entry = pending_by_key.get(cache_key)
    if entry is None:
        raise RuntimeError(f"missing pending cache entry for key {cache_key}")
    source_message = entry["message"]
    future = entry["future"]
    try:
        # `CALL_TIMEOUT_S` governs how long this process waits on the future;
        # the request itself separately receives `timeout_sec` inside `llm_call`.
        classification, elapsed, token_total = future.result(timeout=CALL_TIMEOUT_S)
        _record_llm_attempt_observed(timing, elapsed=elapsed, token_total=token_total)
        completed_by_key[cache_key] = classification
        pending_by_key.pop(cache_key, None)
        return _build_classification_row(message=message, sender_address=sender_address, classification=classification)
    except FutureTimeoutError:
        if timing is not None:
            timing["timeout_count"] = int(timing.get("timeout_count", 0)) + 1
        _record_llm_timeout_observed(timing)
        print(f"LLM call timeout for message {source_message.id}, retrying once", file=sys.stderr)
        future.cancel()
        _record_llm_attempt_submitted(timing)
        retry_future = executor.submit(
            _llm_classify_single_email,
            message=source_message,
            model=model,
            api_key=api_key,
            base_url=base_url,
            max_body_chars=max_body_chars,
            timeout_sec=timeout_sec,
        )
        entry["future"] = retry_future
        try:
            # Retry uses the same executor wait cap; `timeout_sec` still governs
            # the underlying HTTP/network timeout inside the LLM client.
            classification, elapsed, token_total = retry_future.result(timeout=CALL_TIMEOUT_S)
            _record_llm_attempt_observed(timing, elapsed=elapsed, token_total=token_total)
            completed_by_key[cache_key] = classification
            pending_by_key.pop(cache_key, None)
            return _build_classification_row(message=message, sender_address=sender_address, classification=classification)
        except FutureTimeoutError:
            if timing is not None:
                timing["timeout_retry_exhausted_count"] = int(timing.get("timeout_retry_exhausted_count", 0)) + 1
            _record_llm_timeout_observed(timing)
            print(f"LLM call retry timeout for message {source_message.id}, marking uncertain", file=sys.stderr)
            retry_future.cancel()
            pending_by_key.pop(cache_key, None)
            # Do not cache timeout-exhausted uncertain rows. A later identical run
            # is allowed to improve message-level output if the API succeeds.
            return _timed_out_uncertain_row(message)


def _classify_core(
    *,
    messages,
    model: str,
    api_key: str,
    base_url: str,
    max_body_chars: int,
    timeout_sec: int,
    timing: dict[str, object] | None,
    cache_path: str | None,
) -> tuple[dict[int, dict[str, str]], dict[str, dict[str, object]], int]:
    rows_by_index: dict[int, dict[str, str]] = {}
    message_count = 0
    persisted_cache = _load_classification_cache(cache_path)

    with ThreadPoolExecutor(max_workers=LLM_CONCURRENCY_CAP) as executor:
        pending_by_key: dict[str, dict[str, object]] = {}
        completed_by_key: dict[str, dict[str, object]] = dict(persisted_cache)
        pending: list[tuple[int, NormalizedMessage, str, str]] = []
        skipped_count = 0
        candidate_count = 0

        for idx, msg in enumerate(messages):
            message_count = idx + 1
            to_classify, skipped = prefilter_candidates([msg])
            if skipped:
                skipped_count += 1
                rows_by_index[idx] = _prefilter_skipped_row(msg)
                continue

            candidate_count += 1
            if timing is not None and not timing.get("time_to_first_classify_submit_s"):
                pipeline_started = timing.get("_pipeline_started_at")
                if isinstance(pipeline_started, (int, float)):
                    timing["time_to_first_classify_submit_s"] = perf_counter() - float(pipeline_started)

            cache_key, sender_address, cached = _submit_cached_classification_task(
                executor=executor,
                pending_by_key=pending_by_key,
                completed_by_key=completed_by_key,
                message=msg,
                model=model,
                api_key=api_key,
                base_url=base_url,
                max_body_chars=max_body_chars,
                timeout_sec=timeout_sec,
                timing=timing,
            )
            if cached is not None:
                rows_by_index[idx] = _build_classification_row(
                    message=msg,
                    sender_address=sender_address,
                    classification=cached,
                )
                continue
            pending.append((idx, msg, cache_key, sender_address))

        if timing is not None:
            timing["candidate_count"] = candidate_count
            timing["skipped_by_prefilter"] = skipped_count
        print(f"AI prefilter skipped {skipped_count} messages", file=sys.stderr)

        for idx, msg, cache_key, sender_address in pending:
            rows_by_index[idx] = {
                k: str(v)
                for k, v in _resolve_pending_cached_classification(
                    executor=executor,
                    cache_key=cache_key,
                    sender_address=sender_address,
                    pending_by_key=pending_by_key,
                    completed_by_key=completed_by_key,
                    message=msg,
                    model=model,
                    api_key=api_key,
                    base_url=base_url,
                    max_body_chars=max_body_chars,
                    timeout_sec=timeout_sec,
                    timing=timing,
                ).items()
            }

    return rows_by_index, completed_by_key, message_count


def classify_messages_with_llm(
    *,
    messages: list[NormalizedMessage],
    model: str,
    api_key_env: str = "OPENAI_API_KEY",
    base_url: str = "https://api.openai.com/v1",
    max_body_chars: int = 7000,
    timeout_sec: int = 12,
    timing: dict[str, object] | None = None,
    cache_path: str | None = DEFAULT_CLASSIFICATION_CACHE_PATH,
) -> list[dict[str, str]]:
    api_key = _require_api_key(api_key_env)
    classify_started_at = perf_counter()
    if timing is not None:
        _init_timing_defaults(timing)
    rows_by_index, completed_by_key, message_count = _classify_core(
        messages=messages,
        model=model,
        api_key=api_key,
        base_url=base_url,
        max_body_chars=max_body_chars,
        timeout_sec=timeout_sec,
        timing=timing,
        cache_path=cache_path,
    )
    classify_elapsed = perf_counter() - classify_started_at
    out = [rows_by_index[idx] for idx in range(message_count)]
    _finalize_llm_timing(timing, classify_elapsed=classify_elapsed)
    _save_classification_cache(cache_path, completed_by_key)
    return out


def classify_messages_with_llm_streaming(
    *,
    messages,
    model: str,
    api_key_env: str = "OPENAI_API_KEY",
    base_url: str = "https://api.openai.com/v1",
    max_body_chars: int = 7000,
    timeout_sec: int = 12,
    timing: dict[str, object] | None = None,
    cache_path: str | None = DEFAULT_CLASSIFICATION_CACHE_PATH,
) -> list[dict[str, str]]:
    api_key = _require_api_key(api_key_env)
    if timing is not None:
        _init_timing_defaults(timing)

    classify_started_at = perf_counter()
    rows_by_index, completed_by_key, message_count = _classify_core(
        messages=messages,
        model=model,
        api_key=api_key,
        base_url=base_url,
        max_body_chars=max_body_chars,
        timeout_sec=timeout_sec,
        timing=timing,
        cache_path=cache_path,
    )
    _finalize_llm_timing(timing, classify_elapsed=perf_counter() - classify_started_at)
    _save_classification_cache(cache_path, completed_by_key)
    return [rows_by_index[idx] for idx in range(message_count)]


def build_application_rows(message_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    alias_map = _build_domain_alias_map(message_rows)
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in message_rows:
        if r.get("is_job_related") != "true":
            continue
        if not _counts_as_application_event(r):
            continue
        sender = r.get("from_email_address", "")
        if _is_calendar_rsvp_noise(sender, r.get("subject", "")):
            continue
        company = _resolved_row_company(r, alias_map)
        if company:
            app_id = company
        else:
            thread_id = (r.get("thread_id") or "").strip()
            app_id = f"thread:{thread_id}" if thread_id else f"msg:{r.get('gmail_message_id', '')}"
        grouped[app_id].append(r)

    rows: list[dict[str, str]] = []
    for app_id, group in grouped.items():
        normalized_companies = [c for c in (_resolved_row_company(r, alias_map) for r in group) if c]
        company = Counter(normalized_companies).most_common(1)
        position = Counter(_normalize_text(r.get("position", "")) for r in group if _normalize_text(r.get("position", ""))).most_common(1)
        company_val = company[0][0] if company else ""
        position_val = position[0][0] if position else ""

        parsed_dates = []
        for r in group:
            try:
                parsed_dates.append(datetime.fromisoformat(r.get("date", "")))
            except ValueError:
                continue
        if not parsed_dates:
            continue
        application_date = min(parsed_dates)

        best_row = None
        best_status = "Applied"
        best_key = (-1, datetime.min)
        for r in group:
            effective_event_type = _effective_event_type(r)
            status = STATUS_BY_EVENT.get(effective_event_type, "Applied")
            try:
                dt = datetime.fromisoformat(r.get("date", ""))
            except ValueError:
                dt = datetime.min
            key = (STATUS_PRIORITY.get(status, 0), dt)
            if key > best_key:
                best_key = key
                best_row = r
                best_status = status

        assert best_row is not None
        last_event_date = max(parsed_dates)

        rows.append(
            {
                "application_id": app_id,
                "company": company_val,
                "position": position_val,
                "application_date": application_date.date().isoformat(),
                "current_status": best_status,
                "last_event_date": last_event_date.isoformat(),
                "email_count": str(len(group)),
                "evidence_subject": best_row.get("subject", "")[:160],
            }
        )

    rows.sort(key=lambda r: (r["company"], r["position"], r["application_date"]))
    return rows


def write_relevant_emails_csv(path: str, messages: list[NormalizedMessage]) -> str:
    out = Path(path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "gmail_message_id",
                "thread_id",
                "date",
                "from_email_raw",
                "from_email_address",
                "subject",
                "body",
            ],
        )
        writer.writeheader()
        for m in messages:
            writer.writerow(
                {
                    "gmail_message_id": m.id,
                    "thread_id": m.thread_id or "",
                    "date": m.date.isoformat(),
                    "from_email_raw": m.from_email,
                    "from_email_address": _sender_email_address(m.from_email),
                    "subject": m.subject[:200],
                    "body": m.body or m.snippet,
                }
            )
    return str(out)


def write_ai_message_classification_csv(path: str, rows: list[dict[str, str]]) -> str:
    out = Path(path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "gmail_message_id",
        "thread_id",
        "date",
        "from_email_raw",
        "from_email_address",
        "subject",
        "is_job_related",
        "company",
        "position",
        "event_type",
        "status",
        "confidence",
        "meeting_signal",
    ]
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return str(out)


def write_ai_application_table_csv(path: str, rows: list[dict[str, str]]) -> str:
    out = Path(path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "application_id",
        "company",
        "position",
        "application_date",
        "current_status",
        "last_event_date",
        "email_count",
        "evidence_subject",
    ]
    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return str(out)


def build_ai_result_summary(message_rows: list[dict[str, str]]) -> dict[str, int]:
    alias_map = _build_domain_alias_map(message_rows)
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in message_rows:
        if r.get("is_job_related") != "true":
            continue
        if not _counts_as_application_event(r):
            continue
        sender = r.get("from_email_address", "")
        if _is_calendar_rsvp_noise(sender, r.get("subject", "")):
            continue
        company = _resolved_row_company(r, alias_map)
        if company:
            app_id = company
        else:
            thread_id = (r.get("thread_id") or "").strip()
            app_id = f"thread:{thread_id}" if thread_id else f"msg:{r.get('gmail_message_id', '')}"
        grouped[app_id].append(r)

    applications = len(grouped)
    interviews = 0
    no_response = 0
    rejections_total = 0
    rejections_with_interview = 0
    rejections_without_interview = 0
    offers = 0

    for group in grouped.values():
        event_types = {_effective_event_type(r) for r in group}
        has_interview = "interview" in event_types
        has_rejection = "rejection" in event_types
        has_offer = "offer" in event_types
        has_response = has_interview or has_rejection or has_offer

        if has_interview:
            interviews += 1
        if not has_response:
            no_response += 1
        if has_rejection:
            rejections_total += 1
            if has_interview:
                rejections_with_interview += 1
            else:
                rejections_without_interview += 1
        if has_offer:
            offers += 1

    return {
        "applications": applications,
        "interviews": interviews,
        "no_response": no_response,
        "rejections_total": rejections_total,
        "rejections_with_interview": rejections_with_interview,
        "rejections_without_interview": rejections_without_interview,
        "offers": offers,
    }


def write_ai_result_summary_json(path: str, summary: dict[str, int]) -> str:
    out = Path(path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return str(out)


def build_ai_console_summary(summary: dict[str, int]) -> list[str]:
    lines = [
        "AI result summary",
        f"- applications: {summary.get('applications', 0)}",
        f"- interviews: {summary.get('interviews', 0)}",
        f"- no_response: {summary.get('no_response', 0)}",
        f"- rejections (total): {summary.get('rejections_total', 0)}",
        f"- rejections (with interview): {summary.get('rejections_with_interview', 0)}",
        f"- rejections (direct, no interview): {summary.get('rejections_without_interview', 0)}",
        f"- offers: {summary.get('offers', 0)}",
    ]
    return lines
