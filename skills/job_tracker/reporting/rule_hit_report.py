"""Rule-hit confusion reporting for classifier decisions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from statistics import median


@dataclass(slots=True)
class DecisionRow:
    message_id: str
    date: str
    from_domain: str
    subject: str
    thread_id: str | None
    application_key: str
    ignored: bool
    ignore_reason: str | None
    event_type: str | None
    stage: str | None
    confidence: float | None
    rule_id: str | None


def _top_items(values: list[str], topk: int, cap: int = 80) -> str:
    counts: dict[str, int] = {}
    for v in values:
        if not v:
            continue
        counts[v] = counts.get(v, 0) + 1
    ranked = sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:topk]
    return ", ".join(f"{k[:cap]} ({v})" for k, v in ranked)


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    out.extend("| " + " | ".join(r) + " |" for r in rows)
    return "\n".join(out)


def build_rule_hit_report(decisions: list[DecisionRow], topk: int, run_meta: dict[str, str] | None = None) -> str:
    total = len(decisions)
    ignored = [d for d in decisions if d.ignored]
    classified = [d for d in decisions if not d.ignored]

    lines: list[str] = ["# Rule-Hit Confusion Report", ""]

    # A) Run summary
    lines.extend(
        [
            "## A) Run summary",
            f"- total_messages_processed: **{total}**",
            f"- total_ignored: **{len(ignored)}**",
            f"- total_classified: **{len(classified)}**",
            f"- source: **{(run_meta or {}).get('source', '')}**",
            f"- date_range: **{(run_meta or {}).get('date_range', '')}**",
            f"- max_messages: **{(run_meta or {}).get('max_messages', '')}**",
            "",
        ]
    )

    # B) Ignored breakdown
    by_ignore: dict[str, list[DecisionRow]] = {}
    for d in ignored:
        key = d.ignore_reason or "unknown"
        by_ignore.setdefault(key, []).append(d)

    rows_b: list[list[str]] = []
    for reason, group in sorted(by_ignore.items(), key=lambda x: (-len(x[1]), x[0])):
        pct = (len(group) / total * 100) if total else 0.0
        rows_b.append(
            [
                reason,
                str(len(group)),
                f"{pct:.1f}%",
                _top_items([g.from_domain for g in group], 5, cap=80),
                _top_items([g.subject for g in group], 5, cap=80),
            ]
        )

    lines.extend(["## B) Ignored breakdown (by ignore_reason)", _md_table(["ignore_reason", "count", "pct", "top_domains", "top_subjects"], rows_b), ""])

    # C) Rule hits
    by_rule: dict[str, list[DecisionRow]] = {}
    for d in classified:
        key = d.rule_id or "unknown"
        by_rule.setdefault(key, []).append(d)

    rows_c: list[list[str]] = []
    for rule_id, group in sorted(by_rule.items(), key=lambda x: (-len(x[1]), x[0])):
        pct = (len(group) / total * 100) if total else 0.0
        confs = [g.confidence for g in group if g.confidence is not None]
        avg_conf = sum(confs) / len(confs) if confs else 0.0
        et = group[0].event_type or ""
        st = group[0].stage or ""
        rows_c.append(
            [
                rule_id,
                et,
                st,
                str(len(group)),
                f"{pct:.1f}%",
                f"{avg_conf:.2f}",
                _top_items([g.from_domain for g in group], 5, cap=80),
                _top_items([g.subject for g in group], 5, cap=80),
            ]
        )

    lines.extend(["## C) Rule hits (by rule_id)", _md_table(["rule_id", "event_type", "stage", "count", "pct", "avg_conf", "top_domains", "top_subjects"], rows_c), ""])

    # D) Event totals
    by_event: dict[tuple[str, str], list[DecisionRow]] = {}
    for d in classified:
        key = (d.event_type or "", d.stage or "")
        by_event.setdefault(key, []).append(d)

    rows_d: list[list[str]] = []
    for (event_type, stage), group in sorted(by_event.items(), key=lambda x: (-len(x[1]), x[0][0], x[0][1])):
        confs = [g.confidence for g in group if g.confidence is not None]
        avg_conf = sum(confs) / len(confs) if confs else 0.0
        med_conf = median(confs) if confs else 0.0
        rows_d.append(
            [
                event_type,
                stage,
                str(len(group)),
                f"{avg_conf:.2f}",
                f"{med_conf:.2f}",
                _top_items([g.from_domain for g in group], 5, cap=80),
            ]
        )

    lines.extend(["## D) Event type totals (by event_type)", _md_table(["event_type", "stage", "count", "avg_conf", "median_conf", "top_domains"], rows_d), ""])

    # E) Suspicious patterns
    gmail_interview = [d for d in classified if (d.event_type == "interview_invite" and d.from_domain in {"gmail.com", "outlook.com", "yahoo.com"})]
    survey_events = [d for d in classified if ("survey" in d.from_domain or d.from_domain.startswith("recruitmentsurvey"))]
    weak_applied = [d for d in classified if d.rule_id == "application_received:core_phrases" and "update on your application" in d.subject.lower()]

    lines.extend(
        [
            "## E) Suspicious patterns",
            f"- interview_invite on free-mail domains: **{len(gmail_interview)}**",
            f"  - top subjects: {_top_items([d.subject for d in gmail_interview], 5, cap=80)}",
            f"- classified events on survey domains: **{len(survey_events)}**",
            f"  - top subjects: {_top_items([d.subject for d in survey_events], 5, cap=80)}",
            f"- application_received via weak phrase ('update on your application'): **{len(weak_applied)}**",
            f"  - top subjects: {_top_items([d.subject for d in weak_applied], 5, cap=80)}",
            "",
        ]
    )

    # F) Sample lines per top rules
    lines.append("## F) Sample lines per rule (top 10 rules)")
    top_rules = [k for k, _ in sorted(by_rule.items(), key=lambda x: (-len(x[1]), x[0]))[:10]]
    for rule in top_rules:
        group = by_rule[rule][:5]
        lines.append(f"### {rule}")
        lines.append("date | from_domain | confidence | subject")
        lines.append("--- | --- | --- | ---")
        for g in group:
            lines.append(f"{g.date} | {g.from_domain} | {g.confidence if g.confidence is not None else ''} | {g.subject[:120]}")
        lines.append("")

    return "\n".join(lines)


def write_rule_hit_report(path: str, markdown: str) -> None:
    out = Path(path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown, encoding="utf-8")
