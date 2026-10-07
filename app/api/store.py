"""Result storage with automatic deletion after 24 hours.

One JSON file per result, named by a long random token. There are no user accounts:
whoever holds the token can read or delete the result.

Expiry is checked on every read, not only by the cleanup job, so an expired result is
never served even if the job has not run yet.
"""
from __future__ import annotations

import json
import re
import secrets
import time
from pathlib import Path
from typing import Callable, Optional

from app.schema import Report

TTL_SECONDS = 24 * 60 * 60
# token_urlsafe(32) gives 43 characters. Checking the shape also blocks path tricks
# such as "../" in a token.
TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")


class Store:
    def __init__(self, root: Path, ttl: float = TTL_SECONDS, now: Callable[[], float] = time.time):
        self.root, self.ttl, self.now = Path(root), ttl, now
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, token: str) -> Optional[Path]:
        return self.root / f"{token}.json" if TOKEN_RE.match(token) else None

    def save(self, report: Report) -> str:
        token = secrets.token_urlsafe(32)
        data = {"created": self.now(), "report": report.model_dump()}
        self._path(token).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return token

    def _expired(self, created: float) -> bool:
        return self.now() - created >= self.ttl

    def load(self, token: str) -> Optional[Report]:
        path = self._path(token)
        if path is None or not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if self._expired(data["created"]):
            path.unlink(missing_ok=True)
            return None
        return Report.model_validate(data["report"])

    def update(self, token: str, report: Report) -> bool:
        """Save a changed report. Keeps the original time, so edits never extend the 24 hours."""
        if self.load(token) is None:
            return False
        path = self._path(token)
        data = json.loads(path.read_text(encoding="utf-8"))
        data["report"] = report.model_dump()
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return True

    def delete(self, token: str) -> bool:
        path = self._path(token)
        if path is None or not path.exists():
            return False
        path.unlink()
        return True

    def purge_expired(self) -> int:
        """Delete every expired result. Returns how many were deleted."""
        gone = 0
        for path in self.root.glob("*.json"):
            try:
                created = json.loads(path.read_text(encoding="utf-8"))["created"]
            except (OSError, ValueError, KeyError):
                created = 0  # unreadable file: treat as expired rather than keep it forever
            if self._expired(created):
                path.unlink(missing_ok=True)
                gone += 1
        return gone
