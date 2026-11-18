from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from urllib.parse import urlparse


_PORT_RE = re.compile(r"^[0-9]{1,5}$")


def validate_port(value: str) -> int:
    if not _PORT_RE.fullmatch(value.strip()):
        raise ValueError("Port harus berupa angka.")
    port = int(value)
    if not 1 <= port <= 65535:
        raise ValueError("Port harus berada pada rentang 1–65535.")
    return port


def parse_arguments(value: str) -> list[str]:
    raw = (value or "").strip()
    if not raw or raw == "[]":
        return []
    data = None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        if raw.startswith("[") and raw.endswith("]"):
            try:
                parsed = ast.literal_eval(raw)
                if isinstance(parsed, list):
                    data = parsed
            except Exception:
                raise ValueError('Arguments bukan JSON array yang valid. Gunakan format: ["artisan", "serve"].') from None
        if data is None:
            raise ValueError('Arguments harus berbentuk JSON array, contoh: ["artisan", "serve"].') from None

    if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
        raise ValueError('Arguments harus berbentuk JSON array berisi string, contoh: ["artisan", "serve"].')
    if any("\x00" in item or "\n" in item or "\r" in item for item in data):
        raise ValueError("Arguments tidak boleh berisi NUL atau newline.")
    return data


def validate_local_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("Alamat service harus menggunakan http://localhost atau http://127.0.0.1.")
    if parsed.username or parsed.password or not parsed.port:
        raise ValueError("URL service tidak valid.")
    return f"http://127.0.0.1:{parsed.port}"


def validate_workdir(value: str) -> str:
    path = Path(value).expanduser().resolve()
    if not path.is_dir():
        raise ValueError("Project/working directory tidak ditemukan.")
    return str(path)


def validate_hostname_basic(value: str) -> str:
    host = value.strip().lower().rstrip(".")
    if not host:
        return ""
    if len(host) > 253 or ".." in host:
        raise ValueError("Hostname tidak valid.")
    labels = host.split(".")
    for label in labels:
        if not label or len(label) > 63 or not label[0].isalnum() or not label[-1].isalnum():
            raise ValueError("Hostname tidak valid.")
        if any(not (char.isalnum() or char == "-") for char in label):
            raise ValueError("Hostname hanya boleh berisi huruf, angka, dan tanda hubung.")
    return host
