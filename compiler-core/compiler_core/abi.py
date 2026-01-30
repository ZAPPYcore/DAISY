from __future__ import annotations

import hashlib
from typing import Iterable

ABI_VERSION_MAJOR = 2
ABI_VERSION_MINOR = 15


def mangle(module: str, name: str) -> str:
    safe_module = module.replace(".", "__")
    safe_name = name.replace(".", "__")
    return f"daisy_{safe_module}__{safe_name}"


def signature_hash(params: Iterable[str], return_type: str) -> str:
    payload = ",".join(params) + "->" + return_type
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def version_dict() -> dict:
    return {"major": ABI_VERSION_MAJOR, "minor": ABI_VERSION_MINOR}


