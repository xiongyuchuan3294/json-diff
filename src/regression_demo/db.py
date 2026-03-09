from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import pymysql
from pymysql.cursors import DictCursor

from .config import DbConfig


class DbClient:
    def __init__(self, config: DbConfig):
        self.config = config

    def _connect(self, database: str | None = None):
        return pymysql.connect(
            host=self.config.host,
            port=self.config.port,
            database=database or self.config.database,
            user=self.config.user,
            password=self.config.password,
            charset=self.config.charset,
            cursorclass=DictCursor,
            autocommit=False,
        )

    def execute(self, sql: str, params: Iterable[Any] | None = None, database: str | None = None) -> int:
        conn = self._connect(database)
        try:
            with conn.cursor() as cursor:
                affected = cursor.execute(sql, params)
            conn.commit()
            return affected
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def executemany(self, sql: str, params: list[tuple[Any, ...]], database: str | None = None) -> int:
        conn = self._connect(database)
        try:
            with conn.cursor() as cursor:
                affected = cursor.executemany(sql, params)
            conn.commit()
            return affected
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def query(self, sql: str, params: Iterable[Any] | None = None, database: str | None = None) -> list[dict[str, Any]]:
        conn = self._connect(database)
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                return list(cursor.fetchall())
        finally:
            conn.close()

    def query_one(self, sql: str, params: Iterable[Any] | None = None, database: str | None = None) -> dict[str, Any] | None:
        rows = self.query(sql=sql, params=params, database=database)
        return rows[0] if rows else None

    def execute_sql_file(self, path: str | Path, database: str | None = None) -> None:
        content = Path(path).read_text(encoding="utf-8")
        statements = [item.strip() for item in content.split(";\n") if item.strip()]
        conn = self._connect(database)
        try:
            with conn.cursor() as cursor:
                for statement in statements:
                    cursor.execute(statement)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
