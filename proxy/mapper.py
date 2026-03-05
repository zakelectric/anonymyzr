"""
mapper.py
---------
Bidirectional, thread-safe session mapping store.

real_value  ←→  synthetic_value

One session per conversation. Sessions persist in memory for the
lifetime of the proxy process — restart clears all mappings.
"""

import threading
from typing import Optional


class SessionMapper:
    def __init__(self):
        self._lock = threading.Lock()
        self._sessions: dict[str, dict] = {}

    def _get_session(self, session_id: str) -> dict:
        if session_id not in self._sessions:
            self._sessions[session_id] = {
                "real_to_synthetic": {},
                "synthetic_to_real": {},
                "counters": {},
            }
        return self._sessions[session_id]

    def get_synthetic(self, session_id: str, real_value: str) -> Optional[str]:
        with self._lock:
            return self._get_session(session_id)["real_to_synthetic"].get(real_value)

    def get_real(self, session_id: str, synthetic_value: str) -> Optional[str]:
        with self._lock:
            return self._get_session(session_id)["synthetic_to_real"].get(synthetic_value)

    def store(self, session_id: str, real_value: str, synthetic_value: str):
        with self._lock:
            session = self._get_session(session_id)
            session["real_to_synthetic"][real_value] = synthetic_value
            session["synthetic_to_real"][synthetic_value] = real_value

    def get_all_synthetic_to_real(self, session_id: str) -> dict:
        with self._lock:
            return dict(self._get_session(session_id)["synthetic_to_real"])

    def clear_session(self, session_id: str):
        with self._lock:
            self._sessions.pop(session_id, None)

    def list_sessions(self) -> list[str]:
        with self._lock:
            return list(self._sessions.keys())


# Singleton
mapper = SessionMapper()
