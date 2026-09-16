"""As três engrenagens do experimento.

- CapacidadeDoServidor: o limite físico simulado (o que "cai").
- LimitePorCliente: o rate limit (a proteção).
- Contadores: o placar mostrado em GET /status.
"""

from __future__ import annotations

import threading
import time
from collections import deque

RESULTADOS = (
    "recebidas",
    "atendidas_200",
    "bloqueadas_429",
    "recusadas_503",
    "nao_encontradas_404",
)


class CapacidadeDoServidor:
    """Quantas consultas o servidor aguenta ao mesmo tempo.

    Em vez de deixar o computador travar de verdade
    o servidor recusa (HTTP 503) tudo que passa da conta.
    Num servidor real o efeito seria timeout ou conexão recusada.
    """

    def __init__(self, capacidade: int) -> None:
        self._capacidade = capacidade
        self._em_atendimento = 0
        self._trava = threading.Lock()

    def tentar_ocupar_vaga(self) -> bool:
        """Ocupa uma vaga. Devolve False se o servidor está lotado."""
        with self._trava:
            if self._em_atendimento >= self._capacidade:
                return False
            self._em_atendimento += 1
            return True

    def liberar_vaga(self) -> None:
        with self._trava:
            self._em_atendimento -= 1

    @property
    def em_atendimento(self) -> int:
        with self._trava:
            return self._em_atendimento


class LimitePorCliente:
    """Rate limit de janela deslizante.

    Guarda o horário das últimas requisições de cada cliente e deixa passar
    no máximo `limite` delas dentro dos últimos `janela` segundos.
    """

    def __init__(self, limite: int, janela: int) -> None:
        self._limite = limite
        self._janela = janela
        self._historico: dict[str, deque[float]] = {}
        self._trava = threading.Lock()

    def pode_passar(self, cliente: str) -> tuple[bool, int]:
        """Devolve (pode_passar, segundos_para_tentar_de_novo).

        O custo disso é praticamente zero: só olha uma lista de horários.
        É por isso que bloquear sai muito mais barato do que atender.
        """
        agora = time.monotonic()

        with self._trava:
            historico = self._historico.setdefault(cliente, deque())

            # Descarta o que já saiu da janela.
            while historico and agora - historico[0] >= self._janela:
                historico.popleft()

            if len(historico) >= self._limite:
                espera = self._janela - (agora - historico[0])
                return False, max(1, int(espera) + 1)

            historico.append(agora)
            return True, 0

    def limpar(self) -> None:
        with self._trava:
            self._historico.clear()


class Contadores:
    """Placar das duas rotas, exibido em GET /status."""

    def __init__(self, rotas: tuple[str, ...]) -> None:
        self._rotas = rotas
        self._trava = threading.Lock()
        self._placar: dict[str, dict[str, int]] = {}
        self.limpar()

    def registrar(self, rota: str, resultado: str) -> None:
        with self._trava:
            self._placar[rota][resultado] += 1

    def placar(self) -> dict[str, dict[str, int]]:
        with self._trava:
            return {rota: dict(contagem) for rota, contagem in self._placar.items()}

    def limpar(self) -> None:
        with self._trava:
            self._placar = {
                rota: {resultado: 0 for resultado in RESULTADOS}
                for rota in self._rotas
            }
