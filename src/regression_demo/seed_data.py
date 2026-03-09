from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from .config import BATCH_CODE, BATCH_NAME, NEW_SCENARIO_ID, OLD_SCENARIO_ID, TARGET_SCHEMA
from .db import DbClient

BASE_URL = "http://127.0.0.1:9982/aml/wst/custTransInfo?pageSize=10&pageNum=1"
BASE_PATH_PAGE_URL = "http://127.0.0.1:9982/aml/#/taskManagement/caseReportTask/caseView"
START_TIME = datetime(2026, 3, 9, 10, 0, 0)


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _headers(page_suffix: str = "default") -> str:
    return _json({
        "content-type": "application/json;charset=UTF-8",
        "x-page-url": f"{BASE_PATH_PAGE_URL}/{page_suffix}",
        "user-agent": "Codex-Regression-Demo/1.0",
    })


def _request_body(case_no: str, case_date: str = "2020-12-27", model_no: str = "WSTY001") -> str:
    return _json({
        "custId": case_no,
        "caseDate": case_date,
        "modelNo": model_no,
    })


def _query_params() -> str:
    return _json({"pageNum": "1", "pageSize": "10"})


def _response(content: list[dict[str, Any]] | None, *, total_page: int = 1, total_count: int = 0, timestamp: int = 1, success: bool = True, ret_code: int = 0, ret_msg: str = "请求成功") -> str:
    return _json({
        "success": success,
        "retMsg": ret_msg,
        "retCode": ret_code,
        "data": None if content is None else {
            "pageNum": 1,
            "pageSize": 10,
            "totalPage": total_page,
            "totalCount": total_count,
            "content": content,
        },
        "timestamp": timestamp,
    })


def _content(items: list[tuple[str, str, float]]) -> list[dict[str, Any]]:
    rows = []
    for key, direction, amount in items:
        rows.append({
            "transactionkey": key,
            "transTime": "2020-12-27 09:15:00.0",
            "custName": "测试客户",
            "receivePayCd": direction,
            "transAmount": amount,
            "drftNo": f"DRFT-{key}",
            "lastReqNm": "测试公司A",
            "drwrNm": "测试公司B",
            "sensitiveUuid": f"uuid-{key}",
        })
    return rows


def seed_rules(db: DbClient) -> None:
    sql = f"""
    INSERT INTO `{TARGET_SCHEMA}`.`t_compare_rule`
    (`rule_code`,`rule_name`,`scope_type`,`sysid`,`api_path`,`target_json_path`,`ignore_paths`,`array_compare_mode`,`array_key_map`,`priority`,`enabled`,`creator`)
    VALUES
    (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s),
    (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """
    params = [
        (
            "GLOBAL_IGNORE_DYNAMIC",
            "全局动态字段忽略",
            "GLOBAL",
            None,
            None,
            None,
            _json(["$.timestamp"]),
            None,
            None,
            10,
            1,
            "codex",
        ),
        (
            "CUST_TRANS_INFO_ARRAY_BY_KEY",
            "custTransInfo 数组按主键比较",
            "API",
            "aml-web",
            "/aml/wst/custTransInfo",
            None,
            _json([]),
            "BY_KEY",
            _json({"$.data.content": "transactionkey"}),
            20,
            1,
            "codex",
        ),
    ]
    flat: list[Any] = []
    for row in params:
        flat.extend(row)
    db.execute(sql, tuple(flat))


def seed_batch(db: DbClient) -> int:
    db.execute(
        f"""
        INSERT INTO `{TARGET_SCHEMA}`.`t_regression_batch`
        (`batch_code`,`batch_name`,`biz_name`,`old_scenario_id`,`new_scenario_id`,`status`,`operator`,`remark`)
        VALUES (%s,%s,%s,%s,%s,'INIT',%s,%s)
        """,
        (BATCH_CODE, BATCH_NAME, "aml-web", OLD_SCENARIO_ID, NEW_SCENARIO_ID, "codex", "自动化演示任务"),
    )
    row = db.query_one(
        f"SELECT id FROM `{TARGET_SCHEMA}`.`t_regression_batch` WHERE batch_code = %s",
        (BATCH_CODE,),
    )
    assert row is not None
    return int(row["id"])


def seed_request_info(db: DbClient) -> None:
    rows = []
    offset = 0

    def add_row(case_id: str, scenario_id: str, request_body: str, status_code: int, response_body: str, suffix: str, trace_prefix: str, url: str = BASE_URL):
        nonlocal offset
        start_time = START_TIME + timedelta(minutes=offset)
        end_time = start_time + timedelta(milliseconds=420)
        offset += 1
        rows.append((
            f"{trace_prefix}_{offset:03d}",
            "aml-web",
            "127.0.0.1",
            url,
            "POST",
            _headers(suffix),
            _query_params(),
            request_body,
            f"{BASE_PATH_PAGE_URL}/{suffix}",
            scenario_id,
            start_time.strftime("%Y-%m-%d %H:%M:%S"),
            100,
            end_time.strftime("%Y-%m-%d %H:%M:%S"),
            520,
            "trace-stack-demo",
            status_code,
            response_body,
            420,
        ))

    common_old = _content([("TX001", "付", 100.0), ("TX002", "收", 200.0)])
    common_new_same = _content([("TX001", "付", 100.0), ("TX002", "收", 200.0)])
    common_new_reordered = _content([("TX002", "收", 200.0), ("TX001", "付", 100.0)])
    common_new_changed = _content([("TX001", "付", 100.0), ("TX002", "收", 999.0)])

    # TC001 timestamp-only difference
    body_tc001 = _request_body("TC001")
    add_row("TC001", OLD_SCENARIO_ID, body_tc001, 200, _response(common_old, total_page=1, total_count=2, timestamp=1001), "tc001-old", "TC001OLD")
    add_row("TC001", NEW_SCENARIO_ID, body_tc001, 200, _response(common_new_same, total_page=1, total_count=2, timestamp=2002), "tc001-new", "TC001NEW")

    # TC002 normal diff
    body_tc002 = _request_body("TC002")
    add_row("TC002", OLD_SCENARIO_ID, body_tc002, 200, _response(common_old, total_page=1, total_count=2, timestamp=1003), "tc002-old", "TC002OLD")
    add_row("TC002", NEW_SCENARIO_ID, body_tc002, 200, _response(common_old, total_page=2, total_count=20, timestamp=2004), "tc002-new", "TC002NEW")

    # TC003 block diff due retCode/success
    body_tc003 = _request_body("TC003")
    add_row("TC003", OLD_SCENARIO_ID, body_tc003, 200, _response(common_old, total_page=1, total_count=2, timestamp=1005), "tc003-old", "TC003OLD")
    add_row("TC003", NEW_SCENARIO_ID, body_tc003, 200, _response(None, total_page=0, total_count=0, timestamp=2006, success=False, ret_code=500, ret_msg="系统异常"), "tc003-new", "TC003NEW")

    # TC004 reordered array only
    body_tc004 = _request_body("TC004")
    add_row("TC004", OLD_SCENARIO_ID, body_tc004, 200, _response(common_old, total_page=1, total_count=2, timestamp=1007), "tc004-old", "TC004OLD")
    add_row("TC004", NEW_SCENARIO_ID, body_tc004, 200, _response(common_new_reordered, total_page=1, total_count=2, timestamp=2008), "tc004-new", "TC004NEW")

    # TC005 same key changed field
    body_tc005 = _request_body("TC005")
    add_row("TC005", OLD_SCENARIO_ID, body_tc005, 200, _response(common_old, total_page=1, total_count=2, timestamp=1009), "tc005-old", "TC005OLD")
    add_row("TC005", NEW_SCENARIO_ID, body_tc005, 200, _response(common_new_changed, total_page=1, total_count=2, timestamp=2010), "tc005-new", "TC005NEW")

    # TC101 only old
    body_tc101 = _request_body("TC101")
    add_row("TC101", OLD_SCENARIO_ID, body_tc101, 200, _response(common_old, total_page=1, total_count=2, timestamp=1011), "tc101-old", "TC101OLD")

    # TC102 only new
    body_tc102 = _request_body("TC102")
    add_row("TC102", NEW_SCENARIO_ID, body_tc102, 200, _response(common_old, total_page=1, total_count=2, timestamp=2012), "tc102-new", "TC102NEW")

    # TC104 duplicate old
    body_tc104 = _request_body("TC104")
    add_row("TC104", OLD_SCENARIO_ID, body_tc104, 200, _response(common_old, total_page=1, total_count=2, timestamp=1013), "tc104-old-a", "TC104OLDA")
    add_row("TC104", OLD_SCENARIO_ID, body_tc104, 200, _response(common_old, total_page=1, total_count=2, timestamp=1014), "tc104-old-b", "TC104OLDB")
    add_row("TC104", NEW_SCENARIO_ID, body_tc104, 200, _response(common_old, total_page=1, total_count=2, timestamp=2015), "tc104-new", "TC104NEW")

    # TC201 non-200 response
    body_tc201 = _request_body("TC201")
    add_row("TC201", OLD_SCENARIO_ID, body_tc201, 200, _response(common_old, total_page=1, total_count=2, timestamp=1016), "tc201-old", "TC201OLD")
    add_row("TC201", NEW_SCENARIO_ID, body_tc201, 500, _response(None, total_page=0, total_count=0, timestamp=2017, success=False, ret_code=500, ret_msg="服务异常"), "tc201-new", "TC201NEW")

    # TC204 non-json response body
    body_tc204 = _request_body("TC204")
    add_row("TC204", OLD_SCENARIO_ID, body_tc204, 200, _response(common_old, total_page=1, total_count=2, timestamp=1018), "tc204-old", "TC204OLD")
    add_row("TC204", NEW_SCENARIO_ID, body_tc204, 200, "<html><body>500 Internal Server Error</body></html>", "tc204-new", "TC204NEW")

    # TC103 same path but different params should not match and become only_old/only_new
    add_row("TC103_OLD", OLD_SCENARIO_ID, _request_body("TC103_OLD"), 200, _response(common_old, total_page=1, total_count=2, timestamp=1019), "tc103-old", "TC103OLD")
    add_row("TC103_NEW", NEW_SCENARIO_ID, _request_body("TC103_NEW"), 200, _response(common_old, total_page=1, total_count=2, timestamp=2020), "tc103-new", "TC103NEW")

    sql = f"""
    INSERT INTO `{TARGET_SCHEMA}`.`t_request_info`
    (`trace_id`,`sysid`,`client_ip`,`url`,`method`,`headers`,`query_params`,`request_body`,`page_url`,`scenario_id`,`start_time`,`start_time_ms`,`end_time`,`end_time_ms`,`trace_stack_md5`,`status_code`,`response_body`,`duration`)
    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """
    db.executemany(sql, rows)
