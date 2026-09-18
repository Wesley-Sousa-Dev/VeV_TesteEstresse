"""As três engrenagens do experimento.

- ServerCapacity: o limite físico simulado (o que "cai").
- ClientRateLimiter: o rate limit (a proteção).
- Counters: o placar mostrado em GET /status.
"""

from __future__ import annotations

import threading
import time
from collections import deque

RESULTS = (
    "recebidas",
    "atendidas_200",
    "bloqueadas_429",
    "recusadas_503",
    "nao_encontradas_404",
)


class ServerCapacity:
    """Quantas consultas o servidor aguenta ao mesmo tempo.

    Em vez de deixar o computador travar de verdade
    o servidor recusa (HTTP 503) tudo que passa da conta.
    Num servidor real o efeito seria timeout ou conexão recusada.
    """

    def __init__(self, capacity: int) -> None:
        self._capacity = capacity
        self._active_requests = 0
        self._lock = threading.Lock()

    def try_acquire_slot(self) -> bool:
        """Ocupa uma vaga. Devolve False se o servidor está lotado."""
        with self._lock:
            if self._active_requests >= self._capacity:
                return False
            self._active_requests += 1
            return True

    def release_slot(self) -> None:
        with self._lock:
            self._active_requests -= 1

    @property
    def active_requests(self) -> int:
        with self._lock:
            return self._active_requests


class ClientRateLimiter:
    """Rate limit de janela deslizante.

    Guarda o horário das últimas requisições de cada cliente e deixa passar
    no máximo `request_limit` delas dentro dos últimos `window_seconds` segundos.
    """

    def __init__(self, request_limit: int, window_seconds: int) -> None:
        self._request_limit = request_limit
        self._window_seconds = window_seconds
        self._history: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow_request(self, client_id: str) -> tuple[bool, int]:
        """Devolve (allowed, retry_after).

        O custo disso é praticamente zero: só olha uma lista de horários.
        É por isso que bloquear sai muito mais barato do que atender.
        """
        now = time.monotonic()

        with self._lock:
            history = self._history.setdefault(client_id, deque())

            # Descarta o que já saiu da janela.
            while history and now - history[0] >= self._window_seconds:
                history.popleft()

            if len(history) >= self._request_limit:
                retry_after = self._window_seconds - (now - history[0])
                return False, max(1, int(retry_after) + 1)

            history.append(now)
            return True, 0

    def clear(self) -> None:
        with self._lock:
            self._history.clear()


class Counters:
    """Placar das duas rotas, exibido em GET /status."""

    def __init__(self, routes: tuple[str, ...]) -> None:
        self._routes = routes
        self._lock = threading.Lock()
        self._scoreboard: dict[str, dict[str, int]] = {}
        self.clear()

    def record(self, route: str, result: str) -> None:
        with self._lock:
            self._scoreboard[route][result] += 1

    def scoreboard(self) -> dict[str, dict[str, int]]:
        with self._lock:
            return {route: dict(counts) for route, counts in self._scoreboard.items()}

    def clear(self) -> None:
        with self._lock:
            self._scoreboard = {
                route: {result: 0 for result in RESULTS}
                for route in self._routes
            }
