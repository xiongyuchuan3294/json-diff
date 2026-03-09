from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from typing import Sequence

from .config import NEW_SCENARIO_ID, OLD_SCENARIO_ID, TARGET_SCHEMA
from .db import DbClient
from .diff_engine import DiffItem, compare_json_text
from .normalizer import compute_hash, compute_request_fingerprint, normalize_path, normalize_query, normalize_request_body
from .rules import load_rules


def create_regression_batch(
    db: DbClient,
    *,
    batch_code: str,
    batch_name: str,
    old_scenario_id: str,
    new_scenario_id: str,
    biz_name: str = "aml-web",
    operator: str = "codex",
    remark: str = "",
) -> int:
    db.execute(
        f"""
        INSERT INTO `{TARGET_SCHEMA}`.`t_regression_batch`
        (`batch_code`,`batch_name`,`biz_name`,`old_scenario_id`,`new_scenario_id`,`status`,`operator`,`remark`)
        VALUES (%s,%s,%s,%s,%s,'INIT',%s,%s)
        """,
        (batch_code, batch_name, biz_name, old_scenario_id, new_scenario_id, operator, remark),
    )
    row = db.query_one(
        f"SELECT id FROM `{TARGET_SCHEMA}`.`t_regression_batch` WHERE batch_code = %s",
        (batch_code,),
    )
    if not row:
        raise RuntimeError(f"failed to create batch: {batch_code}")
    return int(row["id"])


def build_request_index(
    db: DbClient,
    *,
    scenario_ids: Sequence[str] | None = None,
    api_path: str | None = None,
    api_paths: Sequence[str] | None = None,
    env_tag: str = "runtime",
) -> int:
    where_parts = ["deleted = 0"]
    params: list[str] = []
    if scenario_ids:
        placeholders = ",".join(["%s"] * len(scenario_ids))
        where_parts.append(f"scenario_id IN ({placeholders})")
        params.extend(scenario_ids)
    rows = db.query(
        f"SELECT * FROM `{TARGET_SCHEMA}`.`t_request_info` WHERE {' AND '.join(where_parts)} ORDER BY id",
        tuple(params),
    )

    allowed_paths: set[str] = set()
    if api_paths:
        allowed_paths.update(path for path in api_paths if path)
    if api_path:
        allowed_paths.add(api_path)

    insert_rows = []
    for row in rows:
        normalized_path = normalize_path(row["url"])
        if allowed_paths and normalized_path not in allowed_paths:
            continue
        normalized_query = normalize_query(row.get("query_params"), row["url"])
        normalized_body = normalize_request_body(row.get("request_body"))
        normalized_request_params = normalized_query + normalized_body
        request_fingerprint = compute_request_fingerprint(
            row.get("sysid"),
            row["method"],
            normalized_path,
            normalized_query,
            normalized_body,
        )
        request_hash = compute_hash(normalized_request_params)
        response_hash = compute_hash(row.get("response_body") or "")
        insert_rows.append(
            (
                row["id"],
                row["trace_id"],
                row.get("sysid"),
                row.get("scenario_id"),
                env_tag,
                row["method"],
                normalized_path,
                normalized_query,
                normalized_body,
                normalized_request_params,
                request_fingerprint,
                request_hash,
                response_hash,
                "SUCCESS",
                None,
            )
        )

    if not insert_rows:
        return 0

    sql = f"""
    INSERT INTO `{TARGET_SCHEMA}`.`t_request_compare_index`
    (`request_info_id`,`trace_id`,`sysid`,`scenario_id`,`env_tag`,`method`,`normalized_path`,`normalized_query`,`normalized_body`,`normalized_request_params`,`request_fingerprint`,`request_hash`,`response_hash`,`parse_status`,`parse_error_msg`)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    ON DUPLICATE KEY UPDATE
      `trace_id`=VALUES(`trace_id`),
      `sysid`=VALUES(`sysid`),
      `scenario_id`=VALUES(`scenario_id`),
      `env_tag`=VALUES(`env_tag`),
      `method`=VALUES(`method`),
      `normalized_path`=VALUES(`normalized_path`),
      `normalized_query`=VALUES(`normalized_query`),
      `normalized_body`=VALUES(`normalized_body`),
      `normalized_request_params`=VALUES(`normalized_request_params`),
      `request_fingerprint`=VALUES(`request_fingerprint`),
      `request_hash`=VALUES(`request_hash`),
      `response_hash`=VALUES(`response_hash`),
      `parse_status`=VALUES(`parse_status`),
      `parse_error_msg`=VALUES(`parse_error_msg`),
      `update_time`=CURRENT_TIMESTAMP
    """
    db.executemany(sql, insert_rows)
    return len(insert_rows)


def _load_rule_rows(db: DbClient, path: str) -> list[dict]:
    return db.query(
        f"""
        SELECT * FROM `{TARGET_SCHEMA}`.`t_compare_rule`
        WHERE enabled = 1
          AND (
            scope_type = 'GLOBAL'
            OR (scope_type = 'API' AND api_path = %s)
          )
        ORDER BY priority ASC, id ASC
        """,
        (path,),
    )


def run_regression(
    db: DbClient,
    batch_id: int,
    *,
    old_scenario_id: str = OLD_SCENARIO_ID,
    new_scenario_id: str = NEW_SCENARIO_ID,
    api_path: str | None = None,
    api_paths: Sequence[str] | None = None,
) -> dict[str, int]:
    db.execute(
        f"UPDATE `{TARGET_SCHEMA}`.`t_regression_batch` SET status='RUNNING', start_time=NOW() WHERE id = %s",
        (batch_id,),
    )

    selected_paths: list[str] = []
    if api_paths:
        selected_paths.extend(path for path in api_paths if path)
    if api_path:
        selected_paths.append(api_path)
    selected_paths = list(dict.fromkeys(selected_paths))

    filter_sql = ""
    filter_params: list[str] = []
    if len(selected_paths) == 1:
        filter_sql = " AND idx.normalized_path = %s"
        filter_params.append(selected_paths[0])
    elif len(selected_paths) > 1:
        placeholders = ",".join(["%s"] * len(selected_paths))
        filter_sql = f" AND idx.normalized_path IN ({placeholders})"
        filter_params.extend(selected_paths)

    index_rows = db.query(
        f"""
        SELECT idx.*, req.status_code, req.response_body
        FROM `{TARGET_SCHEMA}`.`t_request_compare_index` idx
        JOIN `{TARGET_SCHEMA}`.`t_request_info` req ON req.id = idx.request_info_id
        WHERE idx.scenario_id IN (%s, %s)
          {filter_sql}
        ORDER BY idx.id ASC
        """,
        tuple([old_scenario_id, new_scenario_id, *filter_params]),
    )

    grouped: dict[str, dict[str, list[dict]]] = defaultdict(lambda: {old_scenario_id: [], new_scenario_id: []})
    for row in index_rows:
        grouped[row["request_fingerprint"]][row["scenario_id"]].append(row)

    stats = Counter()
    for fingerprint, scenario_map in grouped.items():
        old_rows = scenario_map[old_scenario_id]
        new_rows = scenario_map[new_scenario_id]
        sample = (old_rows or new_rows)[0]
        path_value = sample["normalized_path"]
        method = sample["method"]
        sysid = sample["sysid"]

        if len(old_rows) == 0:
            _insert_result(
                db,
                batch_id,
                old_scenario_id,
                new_scenario_id,
                fingerprint,
                sysid,
                method,
                path_value,
                None,
                new_rows[0],
                "ONLY_NEW",
                "SKIPPED",
                "BLOCK",
                0,
                "新版存在但旧版无配对请求",
                [],
            )
            stats["only_new_count"] += 1
            continue

        if len(new_rows) == 0:
            _insert_result(
                db,
                batch_id,
                old_scenario_id,
                new_scenario_id,
                fingerprint,
                sysid,
                method,
                path_value,
                old_rows[0],
                None,
                "ONLY_OLD",
                "SKIPPED",
                "BLOCK",
                0,
                "旧版存在但新版无配对请求",
                [],
            )
            stats["only_old_count"] += 1
            continue

        if len(old_rows) > 1:
            _insert_result(
                db,
                batch_id,
                old_scenario_id,
                new_scenario_id,
                fingerprint,
                sysid,
                method,
                path_value,
                old_rows[0],
                new_rows[0],
                "MULTI_OLD",
                "SKIPPED",
                "BLOCK",
                0,
                f"旧版存在{len(old_rows)}条重复样本",
                [],
            )
            stats["invalid_count"] += 1
            continue

        if len(new_rows) > 1:
            _insert_result(
                db,
                batch_id,
                old_scenario_id,
                new_scenario_id,
                fingerprint,
                sysid,
                method,
                path_value,
                old_rows[0],
                new_rows[0],
                "MULTI_NEW",
                "SKIPPED",
                "BLOCK",
                0,
                f"新版存在{len(new_rows)}条重复样本",
                [],
            )
            stats["invalid_count"] += 1
            continue

        old_row = old_rows[0]
        new_row = new_rows[0]
        rules = load_rules(_load_rule_rows(db, path_value))
        compare_status, diff_level, diffs = compare_json_text(
            old_row.get("response_body"),
            new_row.get("response_body"),
            old_row.get("status_code"),
            new_row.get("status_code"),
            rules,
        )
        summary = _build_summary(compare_status, diff_level, diffs)
        _insert_result(
            db,
            batch_id,
            old_scenario_id,
            new_scenario_id,
            fingerprint,
            sysid,
            method,
            path_value,
            old_row,
            new_row,
            "MATCHED",
            compare_status,
            diff_level,
            len(diffs),
            summary,
            diffs,
        )
        stats["matched_count"] += 1
        if diff_level == "SAME":
            stats["same_count"] += 1
        else:
            stats["diff_count"] += 1
        if diff_level == "BLOCK":
            stats["block_count"] += 1

    total_sample_count = len(index_rows)
    pairable_count = len(grouped)

    db.execute(
        f"""
        UPDATE `{TARGET_SCHEMA}`.`t_regression_batch`
        SET status=%s,
            total_sample_count=%s,
            pairable_count=%s,
            matched_count=%s,
            same_count=%s,
            diff_count=%s,
            only_old_count=%s,
            only_new_count=%s,
            invalid_count=%s,
            block_count=%s,
            end_time=NOW()
        WHERE id=%s
        """,
        (
            "SUCCESS",
            total_sample_count,
            pairable_count,
            stats.get("matched_count", 0),
            stats.get("same_count", 0),
            stats.get("diff_count", 0),
            stats.get("only_old_count", 0),
            stats.get("only_new_count", 0),
            stats.get("invalid_count", 0),
            stats.get("block_count", 0),
            batch_id,
        ),
    )
    return dict(stats)


def _build_summary(compare_status: str, diff_level: str, diffs: list[DiffItem]) -> str:
    if compare_status == "FAILED":
        return diffs[0].rule_source if diffs else "compare failed"
    if diff_level == "SAME":
        return "响应一致"
    if not diffs:
        return f"compare_status={compare_status}, diff_level={diff_level}"
    parts = [f"{item.json_path}:{item.diff_type}" for item in diffs[:3]]
    return "; ".join(parts)


def _insert_result(
    db: DbClient,
    batch_id: int,
    old_scenario_id: str,
    new_scenario_id: str,
    fingerprint: str,
    sysid: str | None,
    method: str,
    api_path: str,
    old_row: dict | None,
    new_row: dict | None,
    pair_status: str,
    compare_status: str,
    diff_level: str,
    diff_count: int,
    summary: str,
    diffs: list[DiffItem],
) -> None:
    rule_snapshot = json.dumps({"generated_at": datetime.now().isoformat()}, ensure_ascii=False)
    db.execute(
        f"""
        INSERT INTO `{TARGET_SCHEMA}`.`t_compare_result`
        (`batch_id`,`old_scenario_id`,`new_scenario_id`,`request_fingerprint`,`sysid`,`method`,`api_path`,`old_request_info_id`,`new_request_info_id`,`old_trace_id`,`new_trace_id`,`pair_status`,`compare_status`,`diff_level`,`diff_count`,`rule_snapshot`,`summary`,`compare_time`)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
        """,
        (
            batch_id,
            old_scenario_id,
            new_scenario_id,
            fingerprint,
            sysid,
            method,
            api_path,
            old_row.get("request_info_id") if old_row else None,
            new_row.get("request_info_id") if new_row else None,
            old_row.get("trace_id") if old_row else None,
            new_row.get("trace_id") if new_row else None,
            pair_status,
            compare_status,
            diff_level,
            diff_count,
            rule_snapshot,
            summary,
        ),
    )
    result_row = db.query_one(
        f"SELECT id FROM `{TARGET_SCHEMA}`.`t_compare_result` WHERE batch_id = %s AND request_fingerprint = %s ORDER BY id DESC LIMIT 1",
        (batch_id, fingerprint),
    )
    if not result_row or not diffs:
        return

    detail_sql = f"""
    INSERT INTO `{TARGET_SCHEMA}`.`t_compare_result_detail`
    (`result_id`,`batch_id`,`json_path`,`diff_type`,`old_value`,`new_value`,`severity`,`rule_source`,`is_ignored`,`sort_no`)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """
    params = []
    for index, item in enumerate(diffs, start=1):
        params.append(
            (
                result_row["id"],
                batch_id,
                item.json_path,
                item.diff_type,
                json.dumps(item.old_value, ensure_ascii=False) if item.old_value is not None else None,
                json.dumps(item.new_value, ensure_ascii=False) if item.new_value is not None else None,
                item.severity,
                item.rule_source,
                item.is_ignored,
                index,
            )
        )
    db.executemany(detail_sql, params)


def collect_report_data(db: DbClient, batch_id: int) -> dict:
    batch = db.query_one(f"SELECT * FROM `{TARGET_SCHEMA}`.`t_regression_batch` WHERE id = %s", (batch_id,))
    results = db.query(
        f"SELECT * FROM `{TARGET_SCHEMA}`.`t_compare_result` WHERE batch_id = %s ORDER BY id",
        (batch_id,),
    )
    detail_counts = db.query(
        f"SELECT severity, COUNT(*) AS cnt FROM `{TARGET_SCHEMA}`.`t_compare_result_detail` WHERE batch_id = %s GROUP BY severity ORDER BY severity",
        (batch_id,),
    )
    return {"batch": batch, "results": results, "detail_counts": detail_counts}
