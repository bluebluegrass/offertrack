"""Main job tracker orchestrator."""

from __future__ import annotations

import re
import json
import random
import csv
import sys
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Literal, Optional

from .classifiers.rules import classify_message_with_meta, get_application_key_info, normalize_message
from .application_summary import (
    SummaryMessageRow,
    build_application_summary_rows,
    build_company_console_summary,
    compute_metrics_from_application_summary,
    write_application_summary_csv,
)
from .ai_classifier import (
    DEFAULT_CLASSIFICATION_CACHE_PATH,
    build_ai_console_summary,
    build_ai_result_summary,
    build_application_rows,
    classify_messages_with_llm,
    classify_messages_with_llm_streaming,
    write_ai_application_table_csv,
    write_ai_message_classification_csv,
    write_ai_result_summary_json,
    write_relevant_emails_csv,
)
from .first_scan import apply_first_scan_filter, build_first_scan_summary, write_first_scan_report
from .metrics import AUDIT_COLUMNS, compute_funnel
from .reporting.domain_debug import build_domain_debug_console_summary, write_domain_report
from .reporting.key_debug import build_key_debug_console_summary, write_key_debug_outputs
from .reporting.reconcile import build_reconcile_console_summary, write_reconcile_outputs
from .reporting.rule_hit_report import DecisionRow, build_rule_hit_report, write_rule_hit_report
from .sankey import render_ai_sankey, render_sankey
from .sources.csv_source import load_csv_messages
from .sources.gmail_readonly import fetch_messages, iter_messages_by_ids
from .sources.outlook_graph import fetch_messages as fetch_outlook_messages
from .sources.sample_source import load_sample_messages
from .types import Event, SkillRunResult


def _extract_domain(from_header: str) -> str:
    """Extracts domain from a 'From' header, handling 'Name <email@domain.com>' format."""
    if not from_header:
        return ""
    # Look for email in angle brackets first
    match = re.search(r"<([^>]+)>", from_header)
    email = match.group(1) if match else from_header
    if "@" in email:
        return email.split("@")[-1].lower().strip()
    return ""

def _run_id() -> str:
    return datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")


def _parse_date(raw: Optional[str]) -> datetime:
    if not raw:
        raise ValueError("start and end are required in YYYY-MM-DD format")
    try:
        return datetime.fromisoformat(raw + "T00:00:00+00:00")
    except ValueError as exc:
        raise ValueError(f"Invalid date '{raw}', expected YYYY-MM-DD") from exc


def _validate_dates(start: Optional[str], end: Optional[str]) -> tuple[datetime, datetime]:
    start_dt = _parse_date(start)
    end_dt = _parse_date(end)
    if start_dt > end_dt:
        raise ValueError("end must be >= start")
    return start_dt, end_dt


def _save_metrics_json(path: Path, result: SkillRunResult) -> None:
    payload = {
        "run_id": result.run_id,
        "metrics": asdict(result.metrics),
        "rates": asdict(result.rates),
        "warnings": result.warnings,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _save_minimal_metadata(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"records": rows}, indent=2), encoding="utf-8")


def _save_audit_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=AUDIT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _emit_ai_timing(timing: dict[str, object]) -> None:
    # Timing semantics:
    # - metadata_fetch_time_s: initial metadata/stub fetch only.
    # - body_fetch_time_s: full duration of the body-fetch stage. In Gmail streaming mode,
    #   this overlaps with LLM classification and must not be added to llm_classify_total_time_s.
    # - llm_classify_total_time_s: wall-clock duration of the classify stage, not a sum of per-call latencies.
    # - fetch_classify_overlap_s: estimated portion of body-fetch time that overlapped classify work.
    # - total_pipeline_wall_time_s: authoritative end-to-end runtime for the whole pipeline.
    # - llm_avg_time_per_call_s: derived wall-clock classify time divided by submitted LLM attempts.
    #   Under concurrency this is not the same as the mean per-call latency.
    payload = {
        "time_to_first_body_s": float(timing.get("time_to_first_body_s", 0.0)),
        "time_to_first_classify_submit_s": float(timing.get("time_to_first_classify_submit_s", 0.0)),
        "total_pipeline_wall_time_s": float(timing.get("total_pipeline_wall_time_s", 0.0)),
        "metadata_fetch_time_s": float(timing.get("metadata_fetch_time_s", 0.0)),
        "body_fetch_time_s": float(timing.get("body_fetch_time_s", 0.0)),
        "candidate_count": int(timing.get("candidate_count", 0)),
        "skipped_by_prefilter": int(timing.get("skipped_by_prefilter", 0)),
        "llm_cache_hits": int(timing.get("llm_cache_hits", 0)),
        "llm_cache_misses": int(timing.get("llm_cache_misses", 0)),
        "llm_concurrency_cap": int(timing.get("llm_concurrency_cap", 0)),
        "llm_classify_total_time_s": float(timing.get("llm_classify_total_time_s", 0.0)),
        "llm_calls_count": int(timing.get("llm_calls_count", 0)),
        "llm_avg_time_per_call_s": float(timing.get("llm_avg_time_per_call_s", 0.0)),
        "llm_p50_time_s": float(timing.get("llm_p50_time_s", 0.0)),
        "llm_p95_time_s": float(timing.get("llm_p95_time_s", 0.0)),
        "llm_max_time_s": float(timing.get("llm_max_time_s", 0.0)),
        "fetch_classify_overlap_s": float(timing.get("fetch_classify_overlap_s", 0.0)),
        "timeout_count": int(timing.get("timeout_count", 0)),
        "timeout_retry_exhausted_count": int(timing.get("timeout_retry_exhausted_count", 0)),
        "fallback_count": int(timing.get("fallback_count", 0)),
        "token_usage_total": int(timing.get("token_usage_total", 0)),
    }
    print(json.dumps(payload, sort_keys=True), file=sys.stderr)


def run(
    source: Literal["gmail", "outlook", "sample", "csv"],
    start: Optional[str],
    end: Optional[str],
    out_dir: str = "output",
    title: str = "Job Search Summary",
    max_messages: int = 2000,
    email: Optional[str] = None,
    credentials_path: str = "credentials.json",
    token_dir: str = ".tokens",
    dry_run: bool = False,
    debug_sample: int = 0,
    audit: bool = False,
    audit_path: str = "output/audit_table.csv",
    report: bool = False,
    report_path: str = "output/rule_report.md",
    report_topk: int = 20,
    csv_path: Optional[str] = None,
    key_debug: bool = False,
    key_debug_dir: str = "output/debug/",
    domain_debug: bool = False,
    domain_debug_path: str = "output/debug/domain_report.csv",
    reconcile: bool = False,
    reconcile_path: str = "output/debug/reconcile_oa.csv",
    gmail_query_mode: Literal["broad", "strict"] = "strict",
    first_scan_report: bool = False,
    first_scan_report_path: str = "output/debug/first_scan_report.csv",
    ai_classify: bool = False,
    ai_model: str = "gpt-4.1-mini",
    ai_api_key_env: str = "OPENAI_API_KEY",
    ai_base_url: str = "https://api.openai.com/v1",
    ai_max_body_chars: int = 7000,
    ai_timeout_sec: int = 12,
    ai_cache_path: str | None = DEFAULT_CLASSIFICATION_CACHE_PATH,
    relevant_emails_path: str = "output/relevant_emails.csv",
    ai_message_classification_path: str = "output/ai_message_classification.csv",
    ai_application_table_path: str = "output/ai_application_table.csv",
    ai_result_summary_path: str = "output/ai_result_summary.json",
    ai_sankey_path: str = "output/ai_sankey.png",
    allow_interactive_auth: bool = True,
) -> SkillRunResult:
    start_dt, end_dt = _validate_dates(start, end)
    start_date = start_dt.date()
    end_date = end_dt.date()

    if max_messages <= 0:
        raise ValueError("max_messages must be > 0")
    if max_messages > 5000:
        raise ValueError("max_messages cap is 5000")

    ai_timing: dict[str, object] = {
        "time_to_first_body_s": 0.0,
        "time_to_first_classify_submit_s": 0.0,
        "total_pipeline_wall_time_s": 0.0,
        "metadata_fetch_time_s": 0.0,
        "body_fetch_time_s": 0.0,
        "candidate_count": 0,
        "skipped_by_prefilter": 0,
        "llm_cache_hits": 0,
        "llm_cache_misses": 0,
        "llm_concurrency_cap": 0,
        "llm_classify_total_time_s": 0.0,
        "llm_calls_count": 0,
        "llm_avg_time_per_call_s": 0.0,
        "llm_p50_time_s": 0.0,
        "llm_p95_time_s": 0.0,
        "llm_max_time_s": 0.0,
        "timeout_count": 0,
        "timeout_retry_exhausted_count": 0,
        "fallback_count": 0,
        "token_usage_total": 0,
    }
    pipeline_started_at = perf_counter()
    ai_timing["_pipeline_started_at"] = pipeline_started_at
    streaming_ai_msg_rows: list[dict[str, str]] | None = None
    streaming_normalized_all: list = []
    if source == "gmail":
        cred_path = Path(credentials_path).expanduser().resolve()
        if not cred_path.exists():
            raise ValueError(f"credentials.json missing: {cred_path}")
        metadata_started = perf_counter()
        raw_messages = fetch_messages(
            email=email,
            start_date=start_date,
            end_date=end_date,
            credentials_path=str(cred_path),
            token_dir=token_dir,
            max_messages=max_messages,
            gmail_query_mode=gmail_query_mode,
            include_body=False,
            allow_interactive_auth=allow_interactive_auth,
        )
        ai_timing["metadata_fetch_time_s"] = perf_counter() - metadata_started
        if ai_classify and raw_messages:
            body_started = perf_counter()
            body_messages: list[dict[str, object]] = []
            normalized_stream: list = []
            first_body_seen = False

            def _iter_normalized_bodies():
                nonlocal first_body_seen
                for raw in iter_messages_by_ids(
                    email=email,
                    credentials_path=str(cred_path),
                    token_dir=token_dir,
                    message_ids=[str(m.get("id", "")) for m in raw_messages if str(m.get("id", ""))][:max_messages],
                    include_body=True,
                    allow_interactive_auth=allow_interactive_auth,
                ):
                    if not first_body_seen:
                        ai_timing["time_to_first_body_s"] = perf_counter() - pipeline_started_at
                        first_body_seen = True
                    body_messages.append(raw)
                    normalized_msg = normalize_message(raw)
                    normalized_stream.append(normalized_msg)
                    yield normalized_msg

            streaming_ai_msg_rows = classify_messages_with_llm_streaming(
                messages=_iter_normalized_bodies(),
                model=ai_model,
                api_key_env=ai_api_key_env,
                base_url=ai_base_url,
                max_body_chars=ai_max_body_chars,
                timeout_sec=ai_timeout_sec,
                timing=ai_timing,
                cache_path=ai_cache_path,
            )
            raw_messages = body_messages
            streaming_normalized_all = normalized_stream
            ai_timing["body_fetch_time_s"] = perf_counter() - body_started
    elif source == "outlook":
        metadata_started = perf_counter()
        raw_messages = fetch_outlook_messages(
            email=email,
            start_date=start_date,
            end_date=end_date,
            token_dir=token_dir,
            max_messages=max_messages,
            include_body=False,
        )
        ai_timing["metadata_fetch_time_s"] = perf_counter() - metadata_started
        if ai_classify and raw_messages:
            body_started = perf_counter()
            raw_messages = fetch_outlook_messages(
                email=email,
                start_date=start_date,
                end_date=end_date,
                token_dir=token_dir,
                max_messages=max_messages,
                include_body=True,
                message_ids=[str(m.get("id", "")) for m in raw_messages if str(m.get("id", ""))],
            )
            ai_timing["body_fetch_time_s"] = perf_counter() - body_started
    elif source == "sample":
        metadata_started = perf_counter()
        raw_messages = load_sample_messages(start_date, end_date)
        ai_timing["metadata_fetch_time_s"] = perf_counter() - metadata_started
    elif source == "csv":
        if not csv_path:
            raise ValueError("csv_path is required for source='csv'")
        metadata_started = perf_counter()
        raw_messages = load_csv_messages(csv_path, start_date, end_date)
        ai_timing["metadata_fetch_time_s"] = perf_counter() - metadata_started
    else:
        raise ValueError(f"Unsupported source: {source}")

    normalized_all = streaming_normalized_all if streaming_normalized_all else [normalize_message(raw) for raw in raw_messages]
    normalized_all.sort(key=lambda m: m.date)
    normalized, first_scan_rows = apply_first_scan_filter(normalized_all)
    normalized.sort(key=lambda m: m.date)

    events: list[Event] = []
    app_has_interview: dict[str, bool] = {}
    decision_rows: list[dict[str, str]] = []
    report_rows: list[DecisionRow] = []
    key_debug_rows: list[dict[str, str]] = []
    domain_debug_rows: list[dict[str, str]] = []
    message_event_counter: Counter[str] = Counter()
    summary_message_rows: list[SummaryMessageRow] = []

    for msg in normalized:
        key_info = get_application_key_info(msg)
        summary_message_rows.append(
            SummaryMessageRow(
                message_id=msg.id,
                thread_id=msg.thread_id or "",
                date=msg.date,
                from_domain=_extract_domain(msg.from_email),
                subject=msg.subject[:160],
                extracted_company_name=key_info.company_name,
                extracted_company_domain=key_info.company_domain,
                role_title=key_info.role_title,
                role_title_confidence=key_info.role_title_confidence,
                application_key=key_info.application_key,
            )
        )
        decision = classify_message_with_meta(msg)

        emitted: list[Event] = []
        for pre_event in decision.events:
            message_event_counter[pre_event.type] += 1
        for event in decision.events:
            if event.type == "interview_reminder":
                if not app_has_interview.get(event.application_key, False):
                    # Downgrade-to-ignore when no prior interview for this application.
                    report_rows.append(
                        DecisionRow(
                            message_id=msg.id,
                            date=msg.date.isoformat(),
                            from_domain=_extract_domain(msg.from_email),
                            subject=msg.subject[:160],
                            thread_id=msg.thread_id,
                            application_key=decision.application_key,
                            ignored=True,
                            ignore_reason="reminder_without_prior_interview",
                            event_type=None,
                            stage=None,
                            confidence=None,
                            rule_id="ignore:reminder_without_prior_interview",
                        )
                    )
                    continue
                event = Event(
                    type="round_update",
                    stage="Interview",
                    occurred_at=event.occurred_at,
                    confidence=event.confidence,
                    evidence=event.evidence,
                    application_key=event.application_key,
                )

            if event.stage == "Interview":
                app_has_interview[event.application_key] = True

            emitted.append(event)
            events.append(event)

        if emitted:
            top = emitted[0]
            report_rows.append(
                DecisionRow(
                    message_id=str(top.evidence.get("message_id", msg.id)),
                    date=top.occurred_at.isoformat(),
                    from_domain=str(top.evidence.get("from_domain", "")),
                    subject=str(top.evidence.get("subject", ""))[:160],
                    thread_id=str(top.evidence.get("thread_id", "")) or msg.thread_id,
                    application_key=top.application_key,
                    ignored=False,
                    ignore_reason=None,
                    event_type=top.type,
                    stage=top.stage,
                    confidence=float(top.confidence),
                    rule_id=decision.rule_id or str(top.evidence.get("pattern", "")),
                )
            )
            decision_rows.append(
                {
                    "date": top.occurred_at.isoformat(),
                    "from_domain": str(top.evidence.get("from_domain", "")),
                    "subject": str(top.evidence.get("subject", "")),
                    "event_type": top.type,
                    "stage": top.stage,
                    "confidence": f"{top.confidence:.2f}",
                    "application_key": top.application_key,
                    "ignored": "false",
                }
            )
            key_debug_rows.append(
                {
                    "gmail_message_id": str(top.evidence.get("message_id", msg.id)),
                    "date": top.occurred_at.isoformat(),
                    "from_domain": str(top.evidence.get("from_domain", "")),
                    "subject": str(top.evidence.get("subject", ""))[:160],
                    "thread_id": str(top.evidence.get("thread_id", "")) or (msg.thread_id or ""),
                    "extracted_company_domain": key_info.company_domain,
                    "extracted_company_name": key_info.company_name,
                    "extracted_role_title": key_info.role_title,
                    "role_title_confidence": f"{key_info.role_title_confidence:.2f}",
                    "built_application_key": key_info.application_key,
                    "key_source": key_info.key_source,
                    "matched_rule_id": decision.rule_id,
                    "event_type": top.type,
                    "stage": top.stage,
                    "confidence": f"{float(top.confidence):.2f}",
                    "ignored": "false",
                    "ignore_reason": "",
                }
            )
            domain_debug_rows.append(
                {
                    "gmail_message_id": str(top.evidence.get("message_id", msg.id)),
                    "date": top.occurred_at.isoformat(),
                    "from_email_domain": str(top.evidence.get("from_domain", "")),
                    "from_email": msg.from_email[:160],
                    "subject": str(top.evidence.get("subject", ""))[:160],
                    "thread_id": str(top.evidence.get("thread_id", "")) or (msg.thread_id or ""),
                    "ignored": "false",
                    "ignore_reason": "",
                    "matched_rule_id": decision.rule_id,
                    "event_type": top.type,
                    "stage": top.stage,
                    "confidence": f"{float(top.confidence):.2f}",
                    "extracted_company_name": key_info.company_name,
                    "extracted_company_domain": key_info.company_domain,
                    "company_domain_source": key_info.company_domain_source,
                    "role_title": key_info.role_title,
                    "role_title_confidence": f"{key_info.role_title_confidence:.2f}",
                    "application_key": key_info.application_key,
                    "key_source": key_info.key_source,
                }
            )
        else:
            report_rows.append(
                DecisionRow(
                    message_id=msg.id,
                    date=msg.date.isoformat(),
                    from_domain=_extract_domain(msg.from_email),
                    subject=msg.subject[:160],
                    thread_id=msg.thread_id,
                    application_key=decision.application_key,
                    ignored=True,
                    ignore_reason=decision.ignore_reason or "ignored",
                    event_type=None,
                    stage=None,
                    confidence=None,
                    rule_id=decision.rule_id or "",
                )
            )
            decision_rows.append(
                {
                    "date": msg.date.isoformat(),
                    "from_domain": _extract_domain(msg.from_email),
                    "subject": msg.subject[:160],
                    "event_type": "",
                    "stage": "",
                    "confidence": "",
                    "application_key": decision.application_key,
                    "ignored": "true",
                }
            )
            key_debug_rows.append(
                {
                    "gmail_message_id": msg.id,
                    "date": msg.date.isoformat(),
                    "from_domain": _extract_domain(msg.from_email),
                    "subject": msg.subject[:160],
                    "thread_id": msg.thread_id or "",
                    "extracted_company_domain": key_info.company_domain,
                    "extracted_company_name": key_info.company_name,
                    "extracted_role_title": key_info.role_title,
                    "role_title_confidence": f"{key_info.role_title_confidence:.2f}",
                    "built_application_key": key_info.application_key,
                    "key_source": key_info.key_source,
                    "matched_rule_id": decision.rule_id,
                    "event_type": "",
                    "stage": "",
                    "confidence": "",
                    "ignored": "true",
                    "ignore_reason": decision.ignore_reason or "ignored",
                }
            )
            domain_debug_rows.append(
                {
                    "gmail_message_id": msg.id,
                    "date": msg.date.isoformat(),
                    "from_email_domain": _extract_domain(msg.from_email),
                    "from_email": msg.from_email[:160],
                    "subject": msg.subject[:160],
                    "thread_id": msg.thread_id or "",
                    "ignored": "true",
                    "ignore_reason": decision.ignore_reason or "ignored",
                    "matched_rule_id": decision.rule_id,
                    "event_type": "",
                    "stage": "",
                    "confidence": "",
                    "extracted_company_name": key_info.company_name,
                    "extracted_company_domain": key_info.company_domain,
                    "company_domain_source": key_info.company_domain_source,
                    "role_title": key_info.role_title,
                    "role_title_confidence": f"{key_info.role_title_confidence:.2f}",
                    "application_key": key_info.application_key,
                    "key_source": key_info.key_source,
                }
            )

    _, _, warnings, audit_rows = compute_funnel(events)
    app_summary_rows = build_application_summary_rows(summary_message_rows, events)
    metrics, rates = compute_metrics_from_application_summary(app_summary_rows)

    run_id = _run_id()
    out = Path(out_dir).expanduser().resolve()
    metrics_path = out / "metrics.json"
    png_path = out / "sankey.png"
    app_summary_path = out / "application_summary.csv"
    metadata_path = out / "metadata_cache.json"
    audit_csv_path = Path(audit_path).expanduser().resolve()

    debug_rows: list[dict[str, str]] = []
    if debug_sample > 0 and decision_rows:
        debug_rows = random.sample(decision_rows, k=min(debug_sample, len(decision_rows)))

    result = SkillRunResult(
        run_id=run_id,
        metrics=metrics,
        rates=rates,
        artifacts={
            "png_path": str(png_path),
            "json_path": str(metrics_path),
            "application_summary_csv_path": str(app_summary_path),
            "audit_csv_path": str(audit_csv_path) if audit else "",
        },
        warnings=warnings,
        debug_samples=debug_rows,
    )

    if ai_classify and not dry_run:
        # AI path classifies the full fetched set so first-scan does not hide late-stage outcomes.
        ai_input_messages = normalized_all
        relevant_csv = write_relevant_emails_csv(relevant_emails_path, ai_input_messages)
        ai_msg_rows = streaming_ai_msg_rows if streaming_ai_msg_rows is not None else classify_messages_with_llm(
            messages=ai_input_messages,
            model=ai_model,
            api_key_env=ai_api_key_env,
            base_url=ai_base_url,
            max_body_chars=ai_max_body_chars,
            timeout_sec=ai_timeout_sec,
            timing=ai_timing,
            cache_path=ai_cache_path,
        )
        ai_msg_csv = write_ai_message_classification_csv(ai_message_classification_path, ai_msg_rows)
        ai_app_rows = build_application_rows(ai_msg_rows)
        ai_app_csv = write_ai_application_table_csv(ai_application_table_path, ai_app_rows)
        ai_summary = build_ai_result_summary(ai_msg_rows)
        ai_summary_json = write_ai_result_summary_json(ai_result_summary_path, ai_summary)
        ai_sankey_png = render_ai_sankey(ai_summary, title, ai_sankey_path)
        result.artifacts["relevant_emails_csv_path"] = relevant_csv
        result.artifacts["ai_message_classification_csv_path"] = ai_msg_csv
        result.artifacts["ai_application_table_csv_path"] = ai_app_csv
        result.artifacts["ai_result_summary_json_path"] = ai_summary_json
        result.artifacts["ai_sankey_png_path"] = ai_sankey_png
        for line in build_ai_console_summary(ai_summary):
            print(line)
        ai_timing["total_pipeline_wall_time_s"] = perf_counter() - pipeline_started_at
        body_window_end = float(ai_timing.get("metadata_fetch_time_s", 0.0)) + float(ai_timing.get("body_fetch_time_s", 0.0))
        first_submit = float(ai_timing.get("time_to_first_classify_submit_s", 0.0))
        ai_timing["fetch_classify_overlap_s"] = max(0.0, body_window_end - first_submit) if first_submit else 0.0
        _emit_ai_timing(ai_timing)

    if not dry_run:
        _save_metrics_json(metrics_path, result)
        write_application_summary_csv(str(app_summary_path), app_summary_rows)
        try:
            render_sankey(metrics, title, str(png_path))
        except Exception as exc:  # noqa: BLE001
            result.warnings.append(f"sankey_render_failed: {exc}")
        if audit:
            _save_audit_csv(audit_csv_path, audit_rows)
        minimal_rows = [
            {
                "id": m.id,
                "thread_id": m.thread_id or "",
                "date": m.date.isoformat(),
                "from_domain": _extract_domain(m.from_email),
                "subject_snippet_hash": next(
                    (str(e.evidence.get("subject_snippet_hash", "")) for e in events if e.evidence.get("message_id") == m.id),
                    "",
                ),
            }
            for m in normalized
        ]
        _save_minimal_metadata(metadata_path, minimal_rows)
    for line in build_company_console_summary(app_summary_rows):
        print(line)

    if first_scan_report:
        path = write_first_scan_report(first_scan_report_path, first_scan_rows)
        result.artifacts["first_scan_report_csv_path"] = path
        for line in build_first_scan_summary(first_scan_rows):
            print(line)

    if report:
        md = build_rule_hit_report(
            report_rows,
            topk=report_topk,
            run_meta={
                "source": source,
                "date_range": f"{start_date.isoformat()}..{end_date.isoformat()}",
                "max_messages": str(max_messages),
            },
        )
        write_rule_hit_report(report_path, md)
        result.artifacts["rule_report_path"] = str(Path(report_path).expanduser().resolve())

    if key_debug:
        debug_paths = write_key_debug_outputs(key_debug_rows, key_debug_dir)
        result.artifacts["applications_debug_csv_path"] = debug_paths["applications_debug"]
        result.artifacts["company_collisions_csv_path"] = debug_paths["company_collisions"]
        result.artifacts["role_extraction_debug_csv_path"] = debug_paths["role_extraction_debug"]
        for line in build_key_debug_console_summary(key_debug_rows):
            print(line)

    if domain_debug:
        report_csv = write_domain_report(domain_debug_path, domain_debug_rows)
        result.artifacts["domain_debug_csv_path"] = report_csv
        for line in build_domain_debug_console_summary(domain_debug_rows):
            print(line)

    if reconcile:
        rec = write_reconcile_outputs(reconcile_path, events, audit_rows)
        result.artifacts["reconcile_csv_path"] = str(rec["reconcile_csv_path"])
        result.artifacts["oa_false_positives_csv_path"] = str(rec["oa_false_positives_csv_path"])
        for line in build_reconcile_console_summary(
            message_event_counter,
            rec["app_count_by_max_stage"],
            int(rec["computed_oa_apps"]),
            int(rec["oa_messages"]),
        ):
            print(line)

    return result


# Backward-compatible alias.
def run_job_tracker(params: object) -> SkillRunResult:
    source = getattr(params, "source", "sample")
    start = getattr(params, "start_date", None)
    end = getattr(params, "end_date", None)

    def as_iso(value: object) -> Optional[str]:
        if value is None:
            return None
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)

    return run(
        source=source,
        start=as_iso(start),
        end=as_iso(end),
        out_dir=getattr(params, "output_dir", "output"),
        title=getattr(params, "title", "Job Search Summary"),
        max_messages=getattr(params, "max_messages", 2000),
        email=getattr(params, "email", None),
        credentials_path=getattr(params, "credentials_path", "credentials.json"),
        token_dir=getattr(params, "token_dir", ".tokens"),
        dry_run=getattr(params, "dry_run", False),
        debug_sample=getattr(params, "debug_sample", 0),
        audit=getattr(params, "audit", False),
        audit_path=getattr(params, "audit_path", "output/audit_table.csv"),
        report=getattr(params, "report", False),
        report_path=getattr(params, "report_path", "output/rule_report.md"),
        report_topk=getattr(params, "report_topk", 20),
        csv_path=getattr(params, "csv_path", None),
        key_debug=getattr(params, "key_debug", False),
        key_debug_dir=getattr(params, "key_debug_dir", "output/debug/"),
        domain_debug=getattr(params, "domain_debug", False),
        domain_debug_path=getattr(params, "domain_debug_path", "output/debug/domain_report.csv"),
        reconcile=getattr(params, "reconcile", False),
        reconcile_path=getattr(params, "reconcile_path", "output/debug/reconcile_oa.csv"),
        gmail_query_mode=getattr(params, "gmail_query_mode", "strict"),
        first_scan_report=getattr(params, "first_scan_report", False),
        first_scan_report_path=getattr(params, "first_scan_report_path", "output/debug/first_scan_report.csv"),
        ai_classify=getattr(params, "ai_classify", False),
        ai_model=getattr(params, "ai_model", "gpt-4.1-mini"),
        ai_api_key_env=getattr(params, "ai_api_key_env", "OPENAI_API_KEY"),
        ai_base_url=getattr(params, "ai_base_url", "https://api.openai.com/v1"),
        ai_max_body_chars=getattr(params, "ai_max_body_chars", 7000),
        ai_timeout_sec=getattr(params, "ai_timeout_sec", 12),
        ai_cache_path=getattr(params, "ai_cache_path", DEFAULT_CLASSIFICATION_CACHE_PATH),
        relevant_emails_path=getattr(params, "relevant_emails_path", "output/relevant_emails.csv"),
        ai_message_classification_path=getattr(params, "ai_message_classification_path", "output/ai_message_classification.csv"),
        ai_application_table_path=getattr(params, "ai_application_table_path", "output/ai_application_table.csv"),
        ai_result_summary_path=getattr(params, "ai_result_summary_path", "output/ai_result_summary.json"),
        ai_sankey_path=getattr(params, "ai_sankey_path", "output/ai_sankey.png"),
        allow_interactive_auth=getattr(params, "allow_interactive_auth", True),
    )
