from __future__ import annotations

import time

from flask import Flask, jsonify, request

from . import config, database
from .limits import ClientRateLimiter, Counters, ServerCapacity

UNPROTECTED_ROUTE = "sem-protecao"
PROTECTED_ROUTE = "com-protecao"

app = Flask(__name__)

database.initialize_database_if_needed()

# Dois "servidores" gêmeos, cada um com a sua própria capacidade. Assim os
# dois cenários podem rodar ao mesmo tempo sem um atrapalhar o outro.
capacities = {
    UNPROTECTED_ROUTE: ServerCapacity(config.CONCURRENT_CAPACITY),
    PROTECTED_ROUTE: ServerCapacity(config.CONCURRENT_CAPACITY),
}
rate_limiter = ClientRateLimiter(config.REQUEST_LIMIT, config.WINDOW_SECONDS)
counters = Counters((UNPROTECTED_ROUTE, PROTECTED_ROUTE))


def _identify_client() -> str:
    """Quem está chamando.

    Em produção seria o endereço IP. Como no teste local todo mundo vem de
    127.0.0.1, os testes mandam o cabeçalho X-Cliente para simular pessoas
    diferentes.
    """
    return request.headers.get("X-Cliente") or request.remote_addr or "desconhecido"


def _query_scores(registration_id: str, route: str):
    """O trabalho em si, idêntico nas duas rotas."""
    capacity = capacities[route]

    if not capacity.try_acquire_slot():
        counters.record(route, "recusadas_503")
        return (
            jsonify({
                "erro": "servidor_sobrecarregado",
                "mensagem": (
                    "O servidor está atendendo mais consultas do que aguenta. "
                    "Sua requisição foi descartada."
                ),
            }),
            503,
        )

    try:
        time.sleep(config.QUERY_DURATION_SECONDS)  # simula um banco lento
        student = database.get_student(registration_id)

        if student is None:
            counters.record(route, "nao_encontradas_404")
            return (
                jsonify({
                    "erro": "inscricao_nao_encontrada",
                    "mensagem": f"Nenhum aluno com a inscrição {registration_id}.",
                }),
                404,
            )

        counters.record(route, "atendidas_200")
        return jsonify(student), 200
    finally:
        capacity.release_slot()


# ---------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------


@app.get("/notas/sem-protecao/<registration_id>")
def get_unprotected_scores(registration_id: str):
    """Aceita tudo que chega. É a rota que cai."""
    counters.record(UNPROTECTED_ROUTE, "recebidas")
    return _query_scores(registration_id, UNPROTECTED_ROUTE)


@app.get("/notas/com-protecao/<registration_id>")
def get_protected_scores(registration_id: str):
    """Igual à de cima, mas confere o rate limit antes de gastar uma vaga."""
    counters.record(PROTECTED_ROUTE, "recebidas")

    allowed, retry_after = rate_limiter.allow_request(_identify_client())
    if not allowed:
        counters.record(PROTECTED_ROUTE, "bloqueadas_429")
        return (
            jsonify({
                "erro": "muitas_requisicoes",
                "mensagem": (
                    f"Você já fez {config.REQUEST_LIMIT} consultas nos "
                    f"últimos {config.WINDOW_SECONDS} segundos. "
                    f"Tente de novo em {retry_after} segundos."
                ),
                "tentar_em_segundos": retry_after,
            }),
            429,
            {"Retry-After": str(retry_after)},
        )

    return _query_scores(registration_id, PROTECTED_ROUTE)


# ---------------------------------------------------------------------------
# Rotas de apoio (não fazem parte da comparação)
# ---------------------------------------------------------------------------


@app.get("/alunos")
def list_students():
    """Lista as inscrições cadastradas, para os testes sortearem uma."""
    return jsonify({"inscricoes": database.list_registrations()})


@app.get("/status")
def get_status():
    """Placar do experimento."""
    return jsonify({
        "configuracao": {
            "capacidade_simultanea": config.CONCURRENT_CAPACITY,
            "tempo_da_consulta_segundos": config.QUERY_DURATION_SECONDS,
            "teto_em_requisicoes_por_segundo": round(
                config.CONCURRENT_CAPACITY / config.QUERY_DURATION_SECONDS, 1
            ),
            "limite_de_requisicoes": config.REQUEST_LIMIT,
            "janela_em_segundos": config.WINDOW_SECONDS,
        },
        "em_atendimento": {
            route: capacity.active_requests for route, capacity in capacities.items()
        },
        "placar": counters.scoreboard(),
    })


@app.post("/status/limpar")
def clear_status():
    """Zera o placar e o histórico do rate limit, para repetir a demonstração."""
    counters.clear()
    rate_limiter.clear()
    return jsonify({"mensagem": "Placar zerado."})


def main() -> None:
    """Sobe o servidor de desenvolvimento do Flask."""
    # Mantém a conexão TCP viva entre requisições. Sem isso, um teste longo no
    # Windows esgota as portas disponíveis e passa a dar erro de conexão.
    from werkzeug.serving import WSGIRequestHandler

    WSGIRequestHandler.protocol_version = "HTTP/1.1"

    print(f"[servidor] http://{config.HOST}:{config.PORT}")
    app.run(host=config.HOST, port=config.PORT, threaded=True)


if __name__ == "__main__":
    main()
