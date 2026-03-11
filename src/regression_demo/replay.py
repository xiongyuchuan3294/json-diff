from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Sequence
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urlparse, urlunparse

from .config import TARGET_SCHEMA
from .db import DbClient
from .normalizer import normalize_path

DEFAULT_SPEED_FACTOR = 1.0
DEFAULT_MIN_GAP_MS = 300
DEFAULT_MAX_GAP_MS = 3000
DEFAULT_TIMEOUT_MS = 10000
DEFAULT_RETRIES = 1

HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


@dataclass
class ReplayHttpResult:
    status_code: int
    response_body: str
    duration_ms: int
    request_start_time: datetime
    request_end_time: datetime
    error_message: str = ""


@dataclass
class ReplayJobParams:
    target_base_url: str
    source_scenario_id: str = ""
    trace_ids: tuple[str, ...] = ()
    api_paths: tuple[str, ...] = ()
    fuzzy_match: bool = False
    speed_factor: float = DEFAULT_SPEED_FACTOR
    min_gap_ms: int = DEFAULT_MIN_GAP_MS
    max_gap_ms: int = DEFAULT_MAX_GAP_MS
    timeout_ms: int = DEFAULT_TIMEOUT_MS
    retries: int = DEFAULT_RETRIES
    replay_code: str = ""
    replay_name: str = "流量回放任务"
    biz_name: str = "aml-web"
    operator: str = "codex"
    remark: str = ""


@dataclass(frozen=True)
class ReplayValidationError:
    code: str
    message: str


def normalize_replay_trace_ids_arg(value: str | None) -> list[str]:
    text = (value or "").strip()
    if not text:
        return []
    rows: list[str] = []
    for item in text.split(","):
        trace_id = item.strip()
        if trace_id:
            rows.append(trace_id)
    return list(dict.fromkeys(rows))


def validate_replay_runtime_options(
    *,
    target_base_url: str,
    replay_speed_factor: float,
    replay_min_gap_ms: int,
    replay_max_gap_ms: int,
    replay_timeout_ms: int,
    replay_retries: int,
) -> ReplayValidationError | None:
    base_url = (target_base_url or "").strip()
    if not base_url:
        return ReplayValidationError(
            code="TARGET_BASE_URL_REQUIRED",
            message="target_base_url is required",
        )
    if not (base_url.startswith("http://") or base_url.startswith("https://")):
        return ReplayValidationError(
            code="TARGET_BASE_URL_SCHEME",
            message="target_base_url must start with http:// or https://",
        )
    if replay_speed_factor <= 0:
        return ReplayValidationError(
            code="SPEED_FACTOR_INVALID",
            message="replay_speed_factor must be > 0",
        )
    if replay_min_gap_ms < 0:
        return ReplayValidationError(
            code="MIN_GAP_INVALID",
            message="replay_min_gap_ms must be >= 0",
        )
    if replay_max_gap_ms < replay_min_gap_ms:
        return ReplayValidationError(
            code="MAX_GAP_INVALID",
            message="replay_max_gap_ms must be >= replay_min_gap_ms",
        )
    if replay_timeout_ms <= 0:
        return ReplayValidationError(
            code="TIMEOUT_INVALID",
            message="replay_timeout_ms must be > 0",
        )
    if replay_retries < 0:
        return ReplayValidationError(
            code="RETRIES_INVALID",
            message="replay_retries must be >= 0",
        )
    return None


def default_replay_code(source_scenario_id: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    source_tag = (source_scenario_id or "source").split("#")[0] or "source"
    return f"RPL_{source_tag}_{timestamp}"


def build_replay_scenario_id(source_scenario_id: str) -> str:
    # Use microseconds to avoid collision when multiple replay jobs start in the same second.
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    source_tag = (source_scenario_id or "source").split("#")[0] or "source"
    return f"{source_tag}#replay#{timestamp}"


def rewrite_url(target_base_url: str, original_url: str) -> str:
    base = urlparse(target_base_url)
    if not base.scheme or not base.netloc:
        raise ValueError(f"invalid replay target base url: {target_base_url}")

    source = urlparse(original_url)
    source_path = source.path or "/"
    prefix_path = (base.path or "").rstrip("/")
    merged_path = f"{prefix_path}{source_path}" if prefix_path else source_path

    return urlunparse((base.scheme, base.netloc, merged_path, "", source.query, ""))


def parse_headers_json(text: str | None) -> dict[str, str]:
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}

    headers: dict[str, str] = {}
    for key, value in payload.items():
        key_text = str(key or "").strip()
        if not key_text or value is None:
            continue
        headers[key_text] = str(value)
    return headers


def sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for key, value in headers.items():
        lower_key = key.strip().lower()
        if not lower_key or lower_key in HOP_BY_HOP_HEADERS:
            continue
        cleaned[key] = value
    return cleaned


def calculate_planned_gap_ms(
    *,
    previous_start_ms: int | None,
    current_start_ms: int | None,
    speed_factor: float,
    min_gap_ms: int,
    max_gap_ms: int,
) -> int:
    if previous_start_ms is None or current_start_ms is None:
        return 0

    recorded_gap = max(0, current_start_ms - previous_start_ms)
    scaled_gap = int(recorded_gap / max(speed_factor, 0.0001))
    return max(min_gap_ms, min(max_gap_ms, scaled_gap))


def _safe_int(value: object) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
    return None


def _request_start_ms(row: dict[str, Any]) -> int | None:
    start_time = _parse_datetime(row.get("start_time"))
    if not start_time:
        return None
    return int(start_time.timestamp() * 1000) + _safe_int(row.get("start_time_ms"))


def _path_matches(path: str, selected_paths: Sequence[str], fuzzy_match: bool) -> bool:
    if not selected_paths:
        return True
    if fuzzy_match:
        return any(path.startswith(item) for item in selected_paths)
    return path in selected_paths


def _sort_replay_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def sort_key(row: dict[str, Any]) -> tuple[datetime, int, int]:
        start_time = _parse_datetime(row.get("start_time")) or datetime.min
        start_time_ms = _safe_int(row.get("start_time_ms"))
        request_id = _safe_int(row.get("id"))
        return start_time, start_time_ms, request_id

    return sorted(rows, key=sort_key)


def _fetch_rows_by_scenario(db: DbClient, source_scenario_id: str) -> list[dict[str, Any]]:
    return db.query(
        f"""
        SELECT *
        FROM `{TARGET_SCHEMA}`.`t_request_info`
        WHERE deleted = 0
          AND scenario_id = %s
        ORDER BY start_time ASC, start_time_ms ASC, id ASC
        """,
        (source_scenario_id,),
    )


def _fetch_rows_by_trace_ids(db: DbClient, trace_ids: Sequence[str]) -> list[dict[str, Any]]:
    placeholders = ",".join(["%s"] * len(trace_ids))
    return db.query(
        f"""
        SELECT *
        FROM `{TARGET_SCHEMA}`.`t_request_info`
        WHERE deleted = 0
          AND trace_id IN ({placeholders})
        ORDER BY start_time ASC, start_time_ms ASC, id ASC
        """,
        tuple(trace_ids),
    )


def load_replay_source_rows(
    db: DbClient,
    *,
    source_scenario_id: str = "",
    trace_ids: Sequence[str] = (),
    api_paths: Sequence[str] = (),
    fuzzy_match: bool = False,
) -> tuple[str, list[dict[str, Any]], int]:
    by_scenario = bool((source_scenario_id or "").strip())
    by_trace = bool(trace_ids)
    if by_scenario == by_trace:
        raise ValueError("exactly one replay selector is required: source_scenario_id or trace_ids")

    rows: list[dict[str, Any]] = []
    resolved_scenario_id = (source_scenario_id or "").strip()
    if by_scenario:
        rows = _fetch_rows_by_scenario(db, resolved_scenario_id)
    else:
        rows = _fetch_rows_by_trace_ids(db, trace_ids)
        found_trace_ids = {str(row.get("trace_id") or "") for row in rows}
        missing = [trace_id for trace_id in trace_ids if trace_id not in found_trace_ids]
        if missing:
            raise ValueError(f"replay trace_id not found: {','.join(missing)}")

        scenarios = {str(row.get("scenario_id") or "").strip() for row in rows if row.get("scenario_id")}
        if len(scenarios) != 1:
            raise ValueError("replay trace_ids must belong to exactly one source scenario_id")
        resolved_scenario_id = next(iter(scenarios))

    total_count = len(rows)
    if not rows:
        return resolved_scenario_id, [], total_count

    selected_paths = [path for path in api_paths if path]
    filtered: list[dict[str, Any]] = []
    for row in rows:
        path = normalize_path(str(row.get("url") or ""))
        if _path_matches(path, selected_paths, fuzzy_match):
            filtered.append(row)
    return resolved_scenario_id, _sort_replay_rows(filtered), total_count


def collect_replay_preflight(
    db: DbClient,
    *,
    source_scenario_id: str = "",
    trace_ids: Sequence[str] = (),
    api_paths: Sequence[str] = (),
    fuzzy_match: bool = False,
) -> dict[str, Any]:
    resolved_scenario_id, selected_rows, total_count = load_replay_source_rows(
        db,
        source_scenario_id=source_scenario_id,
        trace_ids=trace_ids,
        api_paths=api_paths,
        fuzzy_match=fuzzy_match,
    )
    selected_paths = sorted({normalize_path(str(row.get("url") or "")) for row in selected_rows})
    warnings: list[str] = []
    if total_count == 0:
        warnings.append("no source rows found by replay selector")
    if total_count > 0 and len(selected_rows) == 0:
        warnings.append("source rows found but none matched api_paths filter")

    return {
        "mode": "REPLAY",
        "selector_type": "SCENARIO" if source_scenario_id else "TRACE",
        "source_scenario_id": resolved_scenario_id,
        "trace_id_count": len(trace_ids),
        "source_total_count": total_count,
        "selected_count": len(selected_rows),
        "selected_api_paths": selected_paths or ["ALL_API_PATHS"],
        "warnings": warnings,
    }


def create_replay_batch(
    db: DbClient,
    *,
    replay_code: str,
    replay_name: str,
    biz_name: str,
    source_selector_type: str,
    source_scenario_id: str,
    source_trace_ids: str,
    target_base_url: str,
    replay_scenario_id: str,
    speed_factor: float,
    min_gap_ms: int,
    max_gap_ms: int,
    timeout_ms: int,
    retries: int,
    operator: str,
    remark: str,
) -> int:
    db.execute(
        f"""
        INSERT INTO `{TARGET_SCHEMA}`.`t_replay_batch`
        (`replay_code`,`replay_name`,`biz_name`,`source_selector_type`,`source_scenario_id`,`source_trace_ids`,`target_base_url`,`replay_scenario_id`,`speed_factor`,`min_gap_ms`,`max_gap_ms`,`timeout_ms`,`retries`,`status`,`operator`,`remark`)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'INIT',%s,%s)
        """,
        (
            replay_code,
            replay_name,
            biz_name,
            source_selector_type,
            source_scenario_id,
            source_trace_ids,
            target_base_url,
            replay_scenario_id,
            speed_factor,
            min_gap_ms,
            max_gap_ms,
            timeout_ms,
            retries,
            operator,
            remark,
        ),
    )
    row = db.query_one(
        f"SELECT id FROM `{TARGET_SCHEMA}`.`t_replay_batch` WHERE replay_code = %s",
        (replay_code,),
    )
    if not row:
        raise RuntimeError(f"failed to create replay batch: {replay_code}")
    return int(row["id"])


def _update_replay_batch_status(
    db: DbClient,
    replay_batch_id: int,
    *,
    status: str,
    total_count: int,
    success_count: int,
    failed_count: int,
) -> None:
    db.execute(
        f"""
        UPDATE `{TARGET_SCHEMA}`.`t_replay_batch`
        SET `status`=%s,
            `total_count`=%s,
            `success_count`=%s,
            `failed_count`=%s,
            `end_time`=NOW()
        WHERE `id`=%s
        """,
        (status, total_count, success_count, failed_count, replay_batch_id),
    )


def _request_once(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body_text: str,
    timeout_ms: int,
) -> ReplayHttpResult:
    start_perf = time.perf_counter()
    request_start_time = datetime.now()
    payload = body_text.encode("utf-8") if body_text and method not in {"GET", "HEAD"} else None

    req = urllib_request.Request(url=url, data=payload, method=method)
    for key, value in headers.items():
        req.add_header(key, value)

    try:
        with urllib_request.urlopen(req, timeout=max(timeout_ms, 1) / 1000) as response:
            raw = response.read()
            content_type = response.headers.get("Content-Type", "")
            charset = "utf-8"
            if "charset=" in content_type:
                charset = content_type.split("charset=")[-1].split(";")[0].strip() or "utf-8"
            response_body = raw.decode(charset, errors="replace")
            status_code = int(response.getcode() or 200)
    except urllib_error.HTTPError as exc:
        raw = exc.read() if hasattr(exc, "read") else b""
        response_body = raw.decode("utf-8", errors="replace") if raw else str(exc)
        status_code = int(getattr(exc, "code", 500) or 500)
    except Exception as exc:  # noqa: BLE001
        status_code = 599
        response_body = json.dumps(
            {
                "success": False,
                "replay_error": str(exc),
                "error_type": exc.__class__.__name__,
            },
            ensure_ascii=False,
        )

    request_end_time = datetime.now()
    duration_ms = int((time.perf_counter() - start_perf) * 1000)
    return ReplayHttpResult(
        status_code=status_code,
        response_body=response_body,
        duration_ms=max(duration_ms, 0),
        request_start_time=request_start_time,
        request_end_time=request_end_time,
        error_message="" if status_code < 500 else f"http_status={status_code}",
    )


def request_with_retry(
    *,
    method: str,
    url: str,
    headers: dict[str, str],
    body_text: str,
    timeout_ms: int,
    retries: int,
    sleep_func: Callable[[float], None],
) -> ReplayHttpResult:
    max_retries = max(0, retries)
    attempt = 0
    while True:
        result = _request_once(
            method=method,
            url=url,
            headers=headers,
            body_text=body_text,
            timeout_ms=timeout_ms,
        )
        should_retry = result.status_code >= 500 and attempt < max_retries
        if not should_retry:
            return result
        backoff_seconds = 0.2 * (2 ** attempt)
        sleep_func(backoff_seconds)
        attempt += 1


def _insert_replayed_request_info(
    db: DbClient,
    *,
    source_row: dict[str, Any],
    replay_trace_id: str,
    replay_scenario_id: str,
    replay_url: str,
    replay_headers: dict[str, str],
    replay_result: ReplayHttpResult,
) -> int:
    db.execute(
        f"""
        INSERT INTO `{TARGET_SCHEMA}`.`t_request_info`
        (`trace_id`,`sysid`,`client_ip`,`url`,`method`,`headers`,`query_params`,`request_body`,`page_url`,`scenario_id`,`start_time`,`start_time_ms`,`end_time`,`end_time_ms`,`trace_stack_md5`,`status_code`,`response_body`,`duration`,`deleted`)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,0)
        """,
        (
            replay_trace_id,
            source_row.get("sysid"),
            source_row.get("client_ip") or "127.0.0.1",
            replay_url,
            str(source_row.get("method") or "GET").upper(),
            json.dumps(replay_headers, ensure_ascii=False),
            source_row.get("query_params"),
            source_row.get("request_body"),
            source_row.get("page_url"),
            replay_scenario_id,
            replay_result.request_start_time.strftime("%Y-%m-%d %H:%M:%S"),
            int(replay_result.request_start_time.microsecond / 1000),
            replay_result.request_end_time.strftime("%Y-%m-%d %H:%M:%S"),
            int(replay_result.request_end_time.microsecond / 1000),
            source_row.get("trace_stack_md5"),
            replay_result.status_code,
            replay_result.response_body,
            replay_result.duration_ms,
        ),
    )
    row = db.query_one(
        f"SELECT id FROM `{TARGET_SCHEMA}`.`t_request_info` WHERE trace_id = %s",
        (replay_trace_id,),
    )
    if not row:
        raise RuntimeError(f"failed to insert replayed request_info: {replay_trace_id}")
    return int(row["id"])


def _insert_replay_request(
    db: DbClient,
    *,
    replay_batch_id: int,
    seq_no: int,
    source_row: dict[str, Any],
    replay_url: str,
    replay_trace_id: str,
    replay_request_info_id: int,
    replay_result: ReplayHttpResult,
) -> None:
    replay_status = "SUCCESS" if 200 <= replay_result.status_code < 300 else "FAILED"
    db.execute(
        f"""
        INSERT INTO `{TARGET_SCHEMA}`.`t_replay_request`
        (`replay_batch_id`,`seq_no`,`source_request_info_id`,`source_trace_id`,`source_scenario_id`,`request_method`,`source_url`,`replay_url`,`replay_trace_id`,`replay_request_info_id`,`http_status_code`,`duration_ms`,`request_start_time`,`request_end_time`,`replay_status`,`error_message`)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            replay_batch_id,
            seq_no,
            source_row.get("id"),
            source_row.get("trace_id"),
            source_row.get("scenario_id"),
            str(source_row.get("method") or "GET").upper(),
            source_row.get("url"),
            replay_url,
            replay_trace_id,
            replay_request_info_id,
            replay_result.status_code,
            replay_result.duration_ms,
            replay_result.request_start_time.strftime("%Y-%m-%d %H:%M:%S"),
            replay_result.request_end_time.strftime("%Y-%m-%d %H:%M:%S"),
            replay_status,
            replay_result.error_message[:1024] if replay_result.error_message else None,
        ),
    )


def run_replay_job(
    db: DbClient,
    params: ReplayJobParams,
    *,
    dry_run: bool = False,
    request_func: Callable[[str, str, dict[str, str], str, int, int], ReplayHttpResult] | None = None,
    sleep_func: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    source_scenario_id, rows, total_count = load_replay_source_rows(
        db,
        source_scenario_id=params.source_scenario_id,
        trace_ids=params.trace_ids,
        api_paths=params.api_paths,
        fuzzy_match=params.fuzzy_match,
    )
    selected_api_paths = sorted({normalize_path(str(row.get("url") or "")) for row in rows})
    preflight = {
        "mode": "REPLAY",
        "selector_type": "SCENARIO" if params.source_scenario_id else "TRACE",
        "source_scenario_id": source_scenario_id,
        "source_total_count": total_count,
        "selected_count": len(rows),
        "selected_api_paths": selected_api_paths or ["ALL_API_PATHS"],
        "warnings": [],
    }
    if total_count == 0:
        preflight["warnings"].append("no source rows found by replay selector")
    if total_count > 0 and len(rows) == 0:
        preflight["warnings"].append("source rows found but none matched api_paths filter")

    if dry_run:
        return {
            "mode": "DRY_RUN",
            "preflight": preflight,
            "source_scenario_id": source_scenario_id,
            "selected_api_paths": selected_api_paths,
        }

    if not rows:
        raise ValueError("no replay samples selected")

    replay_code = params.replay_code or default_replay_code(source_scenario_id)
    replay_scenario_id = build_replay_scenario_id(source_scenario_id)
    source_selector_type = "SCENARIO" if params.source_scenario_id else "TRACE"
    replay_batch_id = create_replay_batch(
        db,
        replay_code=replay_code,
        replay_name=params.replay_name,
        biz_name=params.biz_name,
        source_selector_type=source_selector_type,
        source_scenario_id=source_scenario_id,
        source_trace_ids=",".join(params.trace_ids),
        target_base_url=params.target_base_url,
        replay_scenario_id=replay_scenario_id,
        speed_factor=params.speed_factor,
        min_gap_ms=params.min_gap_ms,
        max_gap_ms=params.max_gap_ms,
        timeout_ms=params.timeout_ms,
        retries=params.retries,
        operator=params.operator,
        remark=params.remark,
    )
    db.execute(
        f"UPDATE `{TARGET_SCHEMA}`.`t_replay_batch` SET status='RUNNING', start_time=NOW() WHERE id = %s",
        (replay_batch_id,),
    )

    previous_start_ms: int | None = None
    success_count = 0
    failed_count = 0

    for index, row in enumerate(rows, start=1):
        current_start_ms = _request_start_ms(row)
        planned_gap_ms = calculate_planned_gap_ms(
            previous_start_ms=previous_start_ms,
            current_start_ms=current_start_ms,
            speed_factor=max(params.speed_factor, 0.0001),
            min_gap_ms=max(params.min_gap_ms, 0),
            max_gap_ms=max(params.max_gap_ms, max(params.min_gap_ms, 0)),
        )
        if planned_gap_ms > 0:
            sleep_func(planned_gap_ms / 1000)
        if current_start_ms is not None:
            previous_start_ms = current_start_ms

        replay_url = rewrite_url(params.target_base_url, str(row.get("url") or ""))
        replay_headers = sanitize_headers(parse_headers_json(row.get("headers")))
        method = str(row.get("method") or "GET").upper()
        body_text = str(row.get("request_body") or "")

        if request_func:
            replay_result = request_func(method, replay_url, replay_headers, body_text, params.timeout_ms, params.retries)
        else:
            replay_result = request_with_retry(
                method=method,
                url=replay_url,
                headers=replay_headers,
                body_text=body_text,
                timeout_ms=params.timeout_ms,
                retries=params.retries,
                sleep_func=sleep_func,
            )

        replay_trace_id = f"RP_{replay_code}_{index:06d}"[:64]
        replay_request_info_id = _insert_replayed_request_info(
            db,
            source_row=row,
            replay_trace_id=replay_trace_id,
            replay_scenario_id=replay_scenario_id,
            replay_url=replay_url,
            replay_headers=replay_headers,
            replay_result=replay_result,
        )
        _insert_replay_request(
            db,
            replay_batch_id=replay_batch_id,
            seq_no=index,
            source_row=row,
            replay_url=replay_url,
            replay_trace_id=replay_trace_id,
            replay_request_info_id=replay_request_info_id,
            replay_result=replay_result,
        )

        if 200 <= replay_result.status_code < 300:
            success_count += 1
        else:
            failed_count += 1

    status = "SUCCESS" if failed_count == 0 else "PARTIAL_SUCCESS"
    _update_replay_batch_status(
        db,
        replay_batch_id,
        status=status,
        total_count=len(rows),
        success_count=success_count,
        failed_count=failed_count,
    )

    return {
        "mode": "RUN",
        "replay_batch_id": replay_batch_id,
        "replay_code": replay_code,
        "source_scenario_id": source_scenario_id,
        "replay_scenario_id": replay_scenario_id,
        "selected_api_paths": selected_api_paths,
        "stats": {
            "total_count": len(rows),
            "success_count": success_count,
            "failed_count": failed_count,
        },
        "preflight": preflight,
    }
