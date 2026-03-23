#!/usr/bin/env python3
"""Run fast vs enhanced scans on the same input and print a lightweight diff."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from skills.job_tracker.pipeline import run


@dataclass(slots=True)
class ComparableApplicationRow:
    company: str
    position: str
    current_status: str
    evidence_subject: str


def _normalize_text(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _summary_artifact_path(result_artifacts: dict[str, str], *, ai_mode: bool) -> Path:
    if ai_mode:
        return Path(result_artifacts["ai_result_summary_json_path"]).expanduser().resolve()
    return Path(result_artifacts["json_path"]).expanduser().resolve()


def _application_artifact_path(result_artifacts: dict[str, str], *, ai_mode: bool) -> Path:
    if ai_mode:
        return Path(result_artifacts["ai_application_table_csv_path"]).expanduser().resolve()
    return Path(result_artifacts["application_summary_csv_path"]).expanduser().resolve()


def _load_summary(path: Path, *, ai_mode: bool) -> dict[str, int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if ai_mode:
        return {
            "applications": int(payload.get("applications", 0)),
            "interviews": int(payload.get("interviews", 0)),
            "rejections_total": int(payload.get("rejections_total", 0)),
            "offers": int(payload.get("offers", 0)),
            "no_response": int(payload.get("no_response", 0)),
        }

    metrics = payload.get("metrics", {})
    if not isinstance(metrics, dict):
        metrics = {}
    return {
        "applications": int(metrics.get("applications", 0)),
        "interviews": int(metrics.get("interviews", 0)),
        "rejections_total": int(metrics.get("rejected", 0)),
        "offers": int(metrics.get("offers", 0)),
        "no_response": int(metrics.get("no_replies", 0)),
    }


def _load_application_rows(path: Path, *, ai_mode: bool) -> list[ComparableApplicationRow]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    comparable_rows: list[ComparableApplicationRow] = []
    for row in rows:
        if ai_mode:
            comparable_rows.append(
                ComparableApplicationRow(
                    company=row.get("company", ""),
                    position=row.get("position", ""),
                    current_status=row.get("current_status", ""),
                    evidence_subject=row.get("evidence_subject", ""),
                )
            )
        else:
            comparable_rows.append(
                ComparableApplicationRow(
                    company=row.get("company_name", ""),
                    position=row.get("role_title", ""),
                    current_status=row.get("current_status", ""),
                    evidence_subject=row.get("evidence_subject", ""),
                )
            )
    return comparable_rows


def _row_key(row: ComparableApplicationRow) -> tuple[str, str]:
    return (_normalize_text(row.company), _normalize_text(row.position))


def _build_row_index(rows: list[ComparableApplicationRow]) -> dict[tuple[str, str], ComparableApplicationRow]:
    index: dict[tuple[str, str], ComparableApplicationRow] = {}
    for row in rows:
        index[_row_key(row)] = row
    return index


def _compare_summary(fast_summary: dict[str, int], enhanced_summary: dict[str, int]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for key in ("applications", "interviews", "rejections_total", "offers", "no_response"):
        fast_value = int(fast_summary.get(key, 0))
        enhanced_value = int(enhanced_summary.get(key, 0))
        out[key] = {
            "fast": fast_value,
            "enhanced": enhanced_value,
            "delta": fast_value - enhanced_value,
        }
    return out


def _compare_applications(
    fast_rows: list[ComparableApplicationRow],
    enhanced_rows: list[ComparableApplicationRow],
) -> dict[str, Any]:
    fast_index = _build_row_index(fast_rows)
    enhanced_index = _build_row_index(enhanced_rows)

    missing_in_fast: list[dict[str, str]] = []
    extra_in_fast: list[dict[str, str]] = []
    status_changed: list[dict[str, str]] = []

    for key, enhanced_row in enhanced_index.items():
        fast_row = fast_index.get(key)
        if fast_row is None:
            missing_in_fast.append(
                {
                    "company": enhanced_row.company,
                    "position": enhanced_row.position,
                    "enhanced_status": enhanced_row.current_status,
                }
            )
            continue
        if _normalize_text(fast_row.current_status) != _normalize_text(enhanced_row.current_status):
            status_changed.append(
                {
                    "company": enhanced_row.company,
                    "position": enhanced_row.position,
                    "fast_status": fast_row.current_status,
                    "enhanced_status": enhanced_row.current_status,
                }
            )

    for key, fast_row in fast_index.items():
        if key in enhanced_index:
            continue
        extra_in_fast.append(
            {
                "company": fast_row.company,
                "position": fast_row.position,
                "fast_status": fast_row.current_status,
            }
        )

    return {
        "fast_count": len(fast_rows),
        "enhanced_count": len(enhanced_rows),
        "missing_in_fast": missing_in_fast,
        "extra_in_fast": extra_in_fast,
        "status_changed": status_changed,
    }


def _run_mode(
    *,
    mode: str,
    source: str,
    start: str,
    end: str,
    out_dir: Path,
    max_messages: int,
    title: str,
    email: str | None,
    credentials_path: str,
    token_dir: str,
    csv_path: str | None,
    gmail_query_mode: str,
    ai_model: str,
    ai_api_key_env: str,
    ai_base_url: str,
    ai_max_body_chars: int,
    allow_interactive_auth: bool,
):
    mode_out = out_dir / mode
    mode_out.mkdir(parents=True, exist_ok=True)
    return run(
        source=source,
        start=start,
        end=end,
        out_dir=str(mode_out),
        title=title,
        max_messages=max_messages,
        email=email,
        credentials_path=credentials_path,
        token_dir=token_dir,
        csv_path=csv_path,
        gmail_query_mode=gmail_query_mode,
        ai_classify=(mode == "enhanced"),
        ai_model=ai_model,
        ai_api_key_env=ai_api_key_env,
        ai_base_url=ai_base_url,
        ai_max_body_chars=ai_max_body_chars,
        allow_interactive_auth=allow_interactive_auth,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare fast vs enhanced scan outputs.")
    parser.add_argument("--source", choices=["gmail", "outlook", "sample", "csv"], required=True)
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    parser.add_argument("--out", default="output/compare_scan_modes")
    parser.add_argument("--title", default="Job Search Summary")
    parser.add_argument("--max-messages", type=int, default=300)
    parser.add_argument("--email")
    parser.add_argument("--credentials", default="credentials.json")
    parser.add_argument("--token-dir", default=".tokens")
    parser.add_argument("--csv-path")
    parser.add_argument("--gmail-query-mode", choices=["broad", "strict"], default="strict")
    parser.add_argument("--ai-model", default="gpt-4.1-mini")
    parser.add_argument("--ai-api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--ai-base-url", default="https://api.openai.com/v1")
    parser.add_argument("--ai-max-body-chars", type=int, default=7000)
    parser.add_argument("--no-interactive-auth", action="store_true")
    parser.add_argument("--report-json", default="")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Running fast scan...", flush=True)
    fast_result = _run_mode(
        mode="fast",
        source=args.source,
        start=args.start,
        end=args.end,
        out_dir=out_dir,
        max_messages=args.max_messages,
        title=args.title,
        email=args.email,
        credentials_path=args.credentials,
        token_dir=args.token_dir,
        csv_path=args.csv_path,
        gmail_query_mode=args.gmail_query_mode,
        ai_model=args.ai_model,
        ai_api_key_env=args.ai_api_key_env,
        ai_base_url=args.ai_base_url,
        ai_max_body_chars=args.ai_max_body_chars,
        allow_interactive_auth=not args.no_interactive_auth,
    )

    print("Running enhanced scan...", flush=True)
    enhanced_result = _run_mode(
        mode="enhanced",
        source=args.source,
        start=args.start,
        end=args.end,
        out_dir=out_dir,
        max_messages=args.max_messages,
        title=args.title,
        email=args.email,
        credentials_path=args.credentials,
        token_dir=args.token_dir,
        csv_path=args.csv_path,
        gmail_query_mode=args.gmail_query_mode,
        ai_model=args.ai_model,
        ai_api_key_env=args.ai_api_key_env,
        ai_base_url=args.ai_base_url,
        ai_max_body_chars=args.ai_max_body_chars,
        allow_interactive_auth=not args.no_interactive_auth,
    )

    fast_summary = _load_summary(_summary_artifact_path(fast_result.artifacts, ai_mode=False), ai_mode=False)
    enhanced_summary = _load_summary(_summary_artifact_path(enhanced_result.artifacts, ai_mode=True), ai_mode=True)
    fast_rows = _load_application_rows(_application_artifact_path(fast_result.artifacts, ai_mode=False), ai_mode=False)
    enhanced_rows = _load_application_rows(_application_artifact_path(enhanced_result.artifacts, ai_mode=True), ai_mode=True)

    report = {
        "config": {
            "source": args.source,
            "start": args.start,
            "end": args.end,
            "max_messages": args.max_messages,
            "out_dir": str(out_dir),
        },
        "summary_diff": _compare_summary(fast_summary, enhanced_summary),
        "application_diff": _compare_applications(fast_rows, enhanced_rows),
        "artifacts": {
            "fast": fast_result.artifacts,
            "enhanced": enhanced_result.artifacts,
        },
    }

    print("\nSummary diff", flush=True)
    for key, values in report["summary_diff"].items():
        print(
            f"- {key}: fast={values['fast']} enhanced={values['enhanced']} delta={values['delta']}",
            flush=True,
        )

    app_diff = report["application_diff"]
    print("\nApplication diff", flush=True)
    print(f"- fast_count: {app_diff['fast_count']}", flush=True)
    print(f"- enhanced_count: {app_diff['enhanced_count']}", flush=True)
    print(f"- missing_in_fast: {len(app_diff['missing_in_fast'])}", flush=True)
    print(f"- extra_in_fast: {len(app_diff['extra_in_fast'])}", flush=True)
    print(f"- status_changed: {len(app_diff['status_changed'])}", flush=True)

    if app_diff["missing_in_fast"]:
        print("\nMissing in fast (top 10)", flush=True)
        for row in app_diff["missing_in_fast"][:10]:
            print(f"- {row['company']} | {row['position']} | enhanced_status={row['enhanced_status']}", flush=True)

    if app_diff["extra_in_fast"]:
        print("\nExtra in fast (top 10)", flush=True)
        for row in app_diff["extra_in_fast"][:10]:
            print(f"- {row['company']} | {row['position']} | fast_status={row['fast_status']}", flush=True)

    if app_diff["status_changed"]:
        print("\nStatus changed (top 10)", flush=True)
        for row in app_diff["status_changed"][:10]:
            print(
                f"- {row['company']} | {row['position']} | fast={row['fast_status']} enhanced={row['enhanced_status']}",
                flush=True,
            )

    if args.report_json:
        report_path = Path(args.report_json).expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nWrote report: {report_path}", flush=True)


if __name__ == "__main__":
    main()
