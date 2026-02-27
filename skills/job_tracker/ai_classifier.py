"""LLM-based email classification and application-table generation."""

from __future__ import annotations

import csv
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime
from email.utils import parseaddr
from pathlib import Path

from app.utils.llm_client import llm_call
from skills.job_tracker.types import NormalizedMessage

ALLOWED_EVENT_TYPES = {"application", "interview", "rejection", "offer", "other"}
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
CALENDAR_RSVP_PREFIXES = ("accepted:", "tentative accepted:", "declined:")
DOMAIN_PREFIX_CANDIDATES = ("team", "get", "my")
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


def _normalize_text(value: str) -> str:
    out = re.sub(r"[^a-z0-9]+", " ", (value or "").lower())
    return re.sub(r"\s+", " ", out).strip()


def _sender_email_address(raw_from: str) -> str:
    _, addr = parseaddr(raw_from or "")
    return addr.strip().lower()


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
    display = _normalize_text(_sender_display_name(raw_from))
    if not display:
        return ""
    tokens = [t for t in display.split() if t not in GENERIC_SENDER_TOKENS]
    if not tokens:
        return ""
    return _strip_company_suffixes(" ".join(tokens))


def _company_from_text(text: str) -> str:
    roots: list[str] = []
    for match in re.finditer(r"\b([a-z0-9-]+)\.(?:com|co|io|ai|net|org|eu|nl)\b", (text or "").lower()):
        hint = _company_from_domain_root(match.group(1), text)
        if hint:
            roots.append(hint)
    if roots:
        return Counter(roots).most_common(1)[0][0]
    return ""


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
    if _has_meeting_invite_signal(row.get("subject", ""), row.get("body", "")):
        return "interview"
    return "other"


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
    context_text = " ".join([sender_raw or "", subject or "", body or "", c or ""])
    sender_domain_hint = _company_from_sender_domain(sender_addr, context_text)
    text_hint = _company_from_text(context_text)

    if c and c not in PERSONAL_EMAIL_ROOTS and c not in INTERMEDIARY_EMAIL_ROOTS:
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
        display_hint = _company_from_sender_display(sender_raw)
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


def _llm_classify_single_email(
    *,
    message: NormalizedMessage,
    model: str,
    api_key: str,
    base_url: str,
    max_body_chars: int,
    timeout_sec: int,
) -> dict[str, object]:
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
    if _is_calendar_rsvp_noise(sender_address, message.subject):
        is_job_related = False
        event_type = "other"
        company = ""
    elif event_type == "interview" and not _has_meeting_invite_signal(message.subject, message.body or message.snippet):
        event_type = "other"
    return {
        "gmail_message_id": message.id,
        "thread_id": message.thread_id or "",
        "date": message.date.isoformat(),
        "from_email_raw": message.from_email,
        "from_email_address": sender_address,
        "subject": message.subject[:200],
        "is_job_related": "true" if is_job_related else "false",
        "company": company,
        "position": _normalize_text(str(parsed.get("position", ""))),
        "event_type": event_type,
        "status": STATUS_BY_EVENT.get(event_type, "Applied"),
        "confidence": f"{conf:.2f}",
    }


def classify_messages_with_llm(
    *,
    messages: list[NormalizedMessage],
    model: str,
    api_key_env: str = "OPENAI_API_KEY",
    base_url: str = "https://api.openai.com/v1",
    max_body_chars: int = 7000,
    timeout_sec: int = 60,
) -> list[dict[str, str]]:
    api_key = _require_api_key(api_key_env)
    out: list[dict[str, str]] = []
    for msg in messages:
        row = _llm_classify_single_email(
            message=msg,
            model=model,
            api_key=api_key,
            base_url=base_url,
            max_body_chars=max_body_chars,
            timeout_sec=timeout_sec,
        )
        out.append({k: str(v) for k, v in row.items()})
    return out


def build_application_rows(message_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    alias_map = _build_domain_alias_map(message_rows)
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in message_rows:
        if r.get("is_job_related") != "true":
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
