from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from vpsmon.models import Event, VpsOffer

SCHEMA = """
CREATE TABLE IF NOT EXISTS offers (
  source TEXT NOT NULL,
  offer_id TEXT NOT NULL,
  title TEXT NOT NULL,
  provider TEXT NOT NULL,
  price_raw TEXT,
  usd_year REAL,
  available INTEGER NOT NULL,
  stock INTEGER,
  payload_json TEXT NOT NULL DEFAULT '{}',
  first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (source, offer_id)
);

CREATE INDEX IF NOT EXISTS idx_offers_source_seen ON offers(source, last_seen_at);

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  source TEXT NOT NULL,
  offer_id TEXT NOT NULL,
  event_type TEXT NOT NULL,
  title TEXT NOT NULL,
  provider TEXT NOT NULL,
  price_raw TEXT,
  old_price_raw TEXT,
  new_price_raw TEXT,
  usd_year REAL,
  available INTEGER NOT NULL,
  stock INTEGER,
  url TEXT,
  payload_json TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_events_source_created ON events(source, created_at);
CREATE INDEX IF NOT EXISTS idx_events_type_created ON events(event_type, created_at);
"""


class StateStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def get(self, source: str, offer_id: str) -> sqlite3.Row | None:
        cur = self.conn.execute(
            "SELECT * FROM offers WHERE source=? AND offer_id=?",
            (source, offer_id),
        )
        return cur.fetchone()

    def upsert_many(self, offers: Iterable[VpsOffer]) -> None:
        rows = []
        for offer in offers:
            rows.append((
                offer.source,
                offer.offer_id,
                offer.title,
                offer.provider,
                offer.price.raw if offer.price else None,
                offer.price.usd_year if offer.price else None,
                1 if offer.available else 0,
                offer.stock,
            ))
        self.conn.executemany(
            """
            INSERT INTO offers(source, offer_id, title, provider, price_raw, usd_year, available, stock)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source, offer_id) DO UPDATE SET
              title=excluded.title,
              provider=excluded.provider,
              price_raw=excluded.price_raw,
              usd_year=excluded.usd_year,
              available=excluded.available,
              stock=excluded.stock,
              last_seen_at=CURRENT_TIMESTAMP
            """,
            rows,
        )
        self.conn.commit()

    def count_source(self, source: str) -> int:
        cur = self.conn.execute("SELECT count(*) AS n FROM offers WHERE source=?", (source,))
        return int(cur.fetchone()["n"])

    def record_events(self, events: Iterable[Event]) -> None:
        rows = []
        for event in events:
            offer = event.offer
            rows.append((
                offer.source,
                offer.offer_id,
                event.event_type.value,
                offer.title,
                offer.provider,
                offer.price.raw if offer.price else None,
                event.old_price_raw,
                event.new_price_raw,
                offer.price.usd_year if offer.price else None,
                1 if offer.available else 0,
                offer.stock,
                offer.url,
                json.dumps(offer.raw or {}, ensure_ascii=False, sort_keys=True),
            ))
        if not rows:
            return
        self.conn.executemany(
            """
            INSERT INTO events(
              source, offer_id, event_type, title, provider, price_raw, old_price_raw,
              new_price_raw, usd_year, available, stock, url, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        self.conn.commit()
