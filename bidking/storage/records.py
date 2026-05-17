"""记录存储 (JSONL + UUID + 覆盖重写)。

记录字段:
  record_id, timestamp, session_id, strategy, map_id, hero_id,
  inputs, predicted, bid, actual, note, status

status 流转:
  draft -> bid_placed -> completed
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def new_record_id() -> str:
    return uuid.uuid4().hex


def new_session_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def empty_record(strategy_name: str, session_id: str, hero_id: int | None = None) -> dict[str, Any]:
    return {
        "record_id": new_record_id(),
        "timestamp": _now_iso(),
        "session_id": session_id,
        "strategy": strategy_name,
        "map_id": None,
        "hero_id": hero_id,
        "inputs": {},
        "predicted": {},
        "bid": None,
        "actual": {
            "wg": {"count": None, "total_grids": None},
            "blue": {"count": None, "total_grids": None, "total_value": None},
            "purple": {"count": None, "total_grids": None, "total_value": None},
            "gold": {"count": None, "total_grids": None, "total_value": None},
            "red": [],
            "total_value": None,
        },
        "note": "",
        "status": "draft",
    }


class RecordStore:
    """JSONL 文件存储。

    实现策略: 内存维护有序 dict (record_id -> record)，
    每次保存重写整个文件 (atomic via tmp + replace)。
    """

    def __init__(self, path: str | os.PathLike[str]):
        self.path = Path(path)
        self._records: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rid = rec.get("record_id")
                if rid:
                    self._records[rid] = rec

    def _flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for rec in self._records.values():
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        os.replace(tmp, self.path)

    def upsert(self, record: dict[str, Any]) -> None:
        rid = record.get("record_id")
        if not rid:
            rid = new_record_id()
            record["record_id"] = rid
        record["timestamp"] = _now_iso()
        self._records[rid] = record
        self._flush()

    def delete(self, record_id: str) -> None:
        if record_id in self._records:
            del self._records[record_id]
            self._flush()

    def get(self, record_id: str) -> dict[str, Any] | None:
        return self._records.get(record_id)

    def all(self) -> list[dict[str, Any]]:
        return list(self._records.values())

    def latest_draft(self) -> dict[str, Any] | None:
        drafts = [r for r in self._records.values() if r.get("status") == "draft"]
        if not drafts:
            return None
        return max(drafts, key=lambda r: r.get("timestamp", ""))

    def latest_session_id(self) -> str | None:
        if not self._records:
            return None
        latest = max(self._records.values(), key=lambda r: r.get("timestamp", ""))
        return latest.get("session_id")

    def latest_hero_id(self, session_id: str) -> int | None:
        in_session = [r for r in self._records.values() if r.get("session_id") == session_id]
        if not in_session:
            return None
        latest = max(in_session, key=lambda r: r.get("timestamp", ""))
        return latest.get("hero_id")
