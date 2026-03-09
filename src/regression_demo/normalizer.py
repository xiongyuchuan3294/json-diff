from __future__ import annotations

import hashlib
import json
from typing import Any
from urllib.parse import urlparse, parse_qsl


def _normalize_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _normalize_json_value(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_normalize_json_value(item) for item in value]
    return value


def normalize_json_text(text: str | None) -> str:
    if text is None or text == "":
        return ""
    try:
        payload = json.loads(text)
    except Exception:
        return text.strip()
    normalized = _normalize_json_value(payload)
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def normalize_path(url: str) -> str:
    parsed = urlparse(url)
    return parsed.path or url


def normalize_query(query_params_text: str | None, url: str) -> str:
    if query_params_text:
        normalized = normalize_json_text(query_params_text)
        if normalized and normalized != query_params_text.strip():
            return normalized
        try:
            payload = json.loads(query_params_text)
            return json.dumps({key: payload[key] for key in sorted(payload)}, ensure_ascii=False, separators=(",", ":"))
        except Exception:
            pass
    parsed = urlparse(url)
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    if not pairs:
        return ""
    return json.dumps({key: value for key, value in sorted(pairs)}, ensure_ascii=False, separators=(",", ":"))


def normalize_request_body(body_text: str | None) -> str:
    return normalize_json_text(body_text)


def compute_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def compute_request_fingerprint(sysid: str | None, method: str, path: str, normalized_query: str, normalized_body: str) -> str:
    base = "|".join([
        sysid or "",
        method.upper(),
        path,
        normalized_query,
        normalized_body,
    ])
    return compute_hash(base)
