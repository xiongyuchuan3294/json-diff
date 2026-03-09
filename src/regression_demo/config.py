from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class DbConfig:
    host: str
    port: int
    database: str
    user: str
    password: str
    charset: str = "utf8mb4"

    @property
    def raw(self) -> str:
        return f"{self.host},{self.port},{self.database},{self.user},{self.password},{self.charset}"


def _parse_db_conf(raw: str) -> DbConfig:
    parts = [item.strip() for item in raw.split(",")]
    if len(parts) == 5:
        parts.append("utf8mb4")
    if len(parts) != 6:
        raise ValueError("MYSQL_DEMO_CONF should be host,port,database,user,password[,charset]")
    host, port, database, user, password, charset = parts
    return DbConfig(host=host, port=int(port), database=database, user=user, password=password, charset=charset)


def get_demo_db_config() -> DbConfig:
    raw = os.environ.get("MYSQL_DEMO_CONF", "").strip()
    if raw:
        return _parse_db_conf(raw)

    return DbConfig(
        host=os.environ.get("MYSQL_HOST", "127.0.0.1").strip(),
        port=int(os.environ.get("MYSQL_PORT", "3308").strip()),
        database=os.environ.get("MYSQL_DATABASE", "demo_db").strip(),
        user=os.environ.get("MYSQL_USER", "dev").strip(),
        password=os.environ.get("MYSQL_PASSWORD", "123456"),
        charset=os.environ.get("MYSQL_CHARSET", "utf8mb4").strip() or "utf8mb4",
    )


def with_database(config: DbConfig, database: str) -> DbConfig:
    return DbConfig(
        host=config.host,
        port=config.port,
        database=database,
        user=config.user,
        password=config.password,
        charset=config.charset,
    )


TARGET_SCHEMA = os.environ.get("REGRESSION_TARGET_SCHEMA", "rrs_test_dev")
OLD_SCENARIO_ID = os.environ.get("REGRESSION_OLD_SCENARIO_ID", "custTransInfo#old#20260309_01")
NEW_SCENARIO_ID = os.environ.get("REGRESSION_NEW_SCENARIO_ID", "custTransInfo#new#20260309_01")
BATCH_CODE = os.environ.get("REGRESSION_BATCH_CODE", "REGRESSION_DEMO_20260309_01")
BATCH_NAME = os.environ.get("REGRESSION_BATCH_NAME", "custTransInfo 回归演示任务")
