#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""MySQL execution helpers."""

from __future__ import annotations

import logging
from typing import Iterable

import pymysql

from conf.config import get_config


LOGGER = logging.getLogger("mysql_client")
if not LOGGER.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )
    LOGGER.addHandler(handler)
LOGGER.setLevel(logging.INFO)


def resolve_mysql_conf(
    conf_value: str,
    conf_header: str = "mysql",
    conf_file: str = "aml_conf.conf",
) -> str:
    """Resolve either a raw connection string or a named profile."""
    if conf_value.count(",") >= 5:
        return conf_value
    return get_config(conf_value, conf_header=conf_header, conf_file=conf_file)


class Mysql:
    """Simple MySQL client with query and commit helpers."""

    def __init__(
        self,
        conf_value: str,
        conf_header: str = "mysql",
        conf_file: str = "aml_conf.conf",
    ):
        resolved = resolve_mysql_conf(
            conf_value,
            conf_header=conf_header,
            conf_file=conf_file,
        )
        host, port, database, user, password, charset = resolved.split(",")
        self._connection = pymysql.connect(
            host=host,
            port=int(port),
            database=database,
            user=user,
            password=password,
            charset=charset,
            cursorclass=pymysql.cursors.DictCursor,
        )
        self._cursor = self._connection.cursor()
        self._database = database
        LOGGER.info("Connected to MySQL: %s/%s", host, database)

    def query(self, sql: str, num: int | str = ""):
        """Execute a SELECT-like statement."""
        try:
            self._cursor.execute(sql)
            if isinstance(num, int):
                return self._cursor.fetchmany(num)
            if isinstance(num, str) and num.isdigit():
                return self._cursor.fetchmany(int(num))
            return self._cursor.fetchall()
        except Exception:
            self._connection.rollback()
            LOGGER.exception("MySQL query failed")
            return []
        finally:
            self.close()

    def commit(self, sql: str) -> None:
        """Execute a write statement."""
        try:
            self._cursor.execute(sql)
            self._connection.commit()
            LOGGER.info("Executed SQL against %s", self._database)
        except Exception:
            self._connection.rollback()
            LOGGER.exception("MySQL commit failed")
            raise
        finally:
            self.close()

    def insert_sql(self, table_name: str, data: list[dict]) -> None:
        """Insert rows by composing a single INSERT statement."""
        if not data:
            LOGGER.warning("Skip empty insert for table %s", table_name)
            return

        columns = list(data[0].keys())
        rendered_rows = []
        for row in data:
            values = []
            for column in columns:
                value = row.get(column)
                if value is None:
                    values.append("NULL")
                elif isinstance(value, str):
                    values.append("'" + value.replace("'", "''") + "'")
                else:
                    values.append(str(value))
            rendered_rows.append("(" + ",".join(values) + ")")

        sql = (
            f"INSERT INTO {table_name}({','.join(columns)}) VALUES\n"
            + ",\n".join(rendered_rows)
            + ";"
        )
        self.commit(sql)

    def execute_many(self, sql: str, params_list: Iterable[tuple]) -> None:
        """Execute a parameterized batch statement."""
        try:
            self._cursor.executemany(sql, list(params_list))
            self._connection.commit()
            LOGGER.info("Batch executed successfully on %s", self._database)
        except Exception:
            self._connection.rollback()
            LOGGER.exception("MySQL batch execute failed")
            raise
        finally:
            self.close()

    def close(self) -> None:
        if getattr(self, "_cursor", None):
            self._cursor.close()
            self._cursor = None
        if getattr(self, "_connection", None):
            self._connection.close()
            self._connection = None


def op_mysql(
    conf_value: str,
    sql: str,
    op_type: str = "query",
    conf_header: str = "mysql",
    conf_file: str = "aml_conf.conf",
):
    client = Mysql(conf_value, conf_header=conf_header, conf_file=conf_file)
    if op_type == "query":
        return client.query(sql)
    if op_type == "commit":
        client.commit(sql)
        return None
    raise ValueError("op_type must be 'query' or 'commit'")


def insert_mysql(
    conf_value: str,
    table_name: str,
    data: list[dict],
    conf_header: str = "mysql",
    conf_file: str = "aml_conf.conf",
) -> None:
    client = Mysql(conf_value, conf_header=conf_header, conf_file=conf_file)
    client.insert_sql(table_name, data)
