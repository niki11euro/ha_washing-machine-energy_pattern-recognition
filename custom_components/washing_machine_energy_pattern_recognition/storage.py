"""Persistent per-device SQLite archive. All methods are synchronous: use an executor."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .model import Reading, dct_coefficients, energy_kwh, resample


class CycleStorage:
    """Independent archive; never directly edits Home Assistant's recorder DB."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=15000")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS cycles (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  start_ts REAL NOT NULL UNIQUE,
                  end_ts REAL NOT NULL,
                  energy_kwh REAL NOT NULL,
                  max_w REAL NOT NULL,
                  sample_count INTEGER NOT NULL,
                  profile_json TEXT NOT NULL,
                  dct_json TEXT NOT NULL,
                  label TEXT
                );
                CREATE TABLE IF NOT EXISTS samples (
                  cycle_id INTEGER NOT NULL REFERENCES cycles(id),
                  timestamp REAL NOT NULL,
                  power_w REAL NOT NULL,
                  PRIMARY KEY(cycle_id, timestamp)
                );
                CREATE TABLE IF NOT EXISTS active (
                  timestamp REAL PRIMARY KEY,
                  power_w REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS metadata (
                  key TEXT PRIMARY KEY,
                  value TEXT NOT NULL
                );
            """)

    def get_active(self) -> tuple[float | None, list[Reading]]:
        with self._connect() as db:
            row = db.execute("SELECT value FROM metadata WHERE key='active_start'").fetchone()
            start = float(row["value"]) if row else None
            samples = [Reading(float(r[0]), float(r[1])) for r in db.execute(
                "SELECT timestamp,power_w FROM active ORDER BY timestamp"
            )]
        return start, samples

    def save_active(self, start: float, samples: list[Reading]) -> None:
        with self._connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO metadata(key,value) VALUES('active_start',?)", (str(start),)
            )
            db.executemany(
                "INSERT OR REPLACE INTO active(timestamp,power_w) VALUES(?,?)",
                [(r.timestamp, r.power) for r in samples],
            )

    def clear_active(self) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM active")
            db.execute("DELETE FROM metadata WHERE key='active_start'")

    def add_cycle(self, start: float, end: float, samples: list[Reading],
                  *, clear_active: bool = False) -> int | None:
        """Archive exactly once, preserving all raw readings and 30s model bins."""
        if end - start < 60:
            return None
        samples = [r for r in samples if start - 30 <= r.timestamp <= end + 30]
        if not samples:
            return None
        profile = resample(samples, start, end, 30)
        if not profile:
            return None
        with self._connect() as db:
            # Re-running an import should not create near-duplicate cycles.
            duplicate = db.execute(
                "SELECT id FROM cycles WHERE ABS(start_ts-?)<120 LIMIT 1", (start,)
            ).fetchone()
            if duplicate:
                if clear_active:
                    db.execute("DELETE FROM active")
                    db.execute("DELETE FROM metadata WHERE key='active_start'")
                return int(duplicate["id"])
            cursor = db.execute(
                """INSERT INTO cycles(start_ts,end_ts,energy_kwh,max_w,sample_count,
                   profile_json,dct_json) VALUES (?,?,?,?,?,?,?)""",
                (
                    start, end, energy_kwh(samples, start, end),
                    max(r.power for r in samples), len(samples),
                    json.dumps([[b.mean, b.maximum] for b in profile], separators=(",", ":")),
                    json.dumps(dct_coefficients(profile), separators=(",", ":")),
                ),
            )
            cycle_id = int(cursor.lastrowid)
            db.executemany(
                "INSERT OR IGNORE INTO samples(cycle_id,timestamp,power_w) VALUES (?,?,?)",
                [(cycle_id, r.timestamp, r.power) for r in samples],
            )
            if clear_active:
                db.execute("DELETE FROM active")
                db.execute("DELETE FROM metadata WHERE key='active_start'")
        return cycle_id

    def list_cycles(self) -> list[dict]:
        with self._connect() as db:
            rows = db.execute("""SELECT id,start_ts,end_ts,energy_kwh,max_w,
                sample_count,profile_json,dct_json,label FROM cycles ORDER BY start_ts""").fetchall()
        return [
            {
                "id": int(r["id"]), "start": float(r["start_ts"]),
                "end": float(r["end_ts"]), "energy_kwh": float(r["energy_kwh"]),
                "max_w": float(r["max_w"]), "sample_count": int(r["sample_count"]),
                "profile": json.loads(r["profile_json"]),
                "dct": json.loads(r["dct_json"]), "label": r["label"],
            }
            for r in rows
        ]

    def label_cycle(self, cycle_id: int, label: str) -> bool:
        with self._connect() as db:
            cur = db.execute("UPDATE cycles SET label=? WHERE id=?", (label.strip()[:80], cycle_id))
            return cur.rowcount > 0
