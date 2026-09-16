from __future__ import annotations

import time

from flask import Flask, jsonify, request

from . import banco, config
from .limites import CapacidadeDoServidor, Contadores, LimitePorCliente

ROTA_SEM_PROTECAO = "sem-protecao"
ROTA_COM_PROTECAO = "com-protecao"

app = Flask(__name__)

banco.criar_banco_se_necessario()

# Dois "servidores" gêmeos, cada um com a sua própria capacidade. Assim os
# dois cenários podem rodar ao mesmo tempo sem um atrapalhar o outro.
capacidades = {
    ROTA_SEM_PROTECAO: CapacidadeDoServidor(config.CAPACIDADE_SIMULTANEA),
    ROTA_COM_PROTECAO: CapacidadeDoServidor(config.CAPACIDADE_SIMULTANEA),
}
limite = LimitePorCliente(config.LIMITE_DE_REQUISICOES, config.JANELA_EM_SEGUNDOS)
contadores = Contadores((ROTA_SEM_PROTECAO, ROTA_COM_PROTECAO))


def _identificar_cliente() -> str:
    """Quem está chamando.

    Em produção seria o endereço IP. Como no teste local todo mundo vem de
    127.0.0.1, os testes mandam o cabeçalho X-Cliente para simular pessoas
    diferentes.
    """
    return request.headers.get("X-Cliente") or request.remote_addr or "desconhecido"


def _consultar_notas(inscricao: str, rota: str):
    """O trabalho em si, idêntico nas duas rotas."""
    capacidade = capacidades[rota]

    if not capacidade.tentar_ocupar_vaga():
        contadores.registrar(rota, "recusadas_503")
        return (
            jsonify(
                erro="servidor_sobrecarregado",
                mensagem=(
                    "O servidor está atendendo mais consultas do que aguenta. "
                    "Sua requisição foi descartada."
                ),
            ),
            503,
        )

    try:
        time.sleep(config.TEMPO_DA_CONSULTA_SEGUNDOS)  # simula um banco lento
        aluno = banco.buscar_aluno(inscricao)

        if aluno is None:
            contadores.registrar(rota, "nao_encontradas_404")
            return (
                jsonify(
                    erro="inscricao_nao_encontrada",
                    mensagem=f"Nenhum aluno com a inscrição {inscricao}.",
                ),
                404,
            )

        contadores.registrar(rota, "atendidas_200")
        return jsonify(aluno), 200
    finally:
        capacidade.liberar_vaga()


# ---------------------------------------------------------------------------
# Rotas
# ---------------------------------------------------------------------------


@app.get("/notas/sem-protecao/<inscricao>")
def notas_sem_protecao(inscricao: str):
    """Aceita tudo que chega. É a rota que cai."""
    contadores.registrar(ROTA_SEM_PROTECAO, "recebidas")
    return _consultar_notas(inscricao, ROTA_SEM_PROTECAO)


@app.get("/notas/com-protecao/<inscricao>")
def notas_com_protecao(inscricao: str):
    """Igual à de cima, mas confere o rate limit antes de gastar uma vaga."""
    contadores.registrar(ROTA_COM_PROTECAO, "recebidas")

    pode_passar, espera = limite.pode_passar(_identificar_cliente())
    if not pode_passar:
        contadores.registrar(ROTA_COM_PROTECAO, "bloqueadas_429")
        return (
            jsonify(
                erro="muitas_requisicoes",
                mensagem=(
                    f"Você já fez {config.LIMITE_DE_REQUISICOES} consultas nos "
                    f"últimos {config.JANELA_EM_SEGUNDOS} segundos. "
                    f"Tente de novo em {espera} segundos."
                ),
                tentar_em_segundos=espera,
            ),
            429,
            {"Retry-After": str(espera)},
        )

    return _consultar_notas(inscricao, ROTA_COM_PROTECAO)


# ---------------------------------------------------------------------------
# Rotas de apoio (não fazem parte da comparação)
# ---------------------------------------------------------------------------


@app.get("/alunos")
def listar_alunos():
    """Lista as inscrições cadastradas, para os testes sortearem uma."""
    return jsonify(inscricoes=banco.listar_inscricoes())


@app.get("/status")
def status():
    """Placar do experimento."""
    return jsonify(
        configuracao={
            "capacidade_simultanea": config.CAPACIDADE_SIMULTANEA,
            "tempo_da_consulta_segundos": config.TEMPO_DA_CONSULTA_SEGUNDOS,
            "teto_em_requisicoes_por_segundo": round(
                config.CAPACIDADE_SIMULTANEA / config.TEMPO_DA_CONSULTA_SEGUNDOS, 1
            ),
            "limite_de_requisicoes": config.LIMITE_DE_REQUISICOES,
            "janela_em_segundos": config.JANELA_EM_SEGUNDOS,
        },
        em_atendimento={
            rota: capacidade.em_atendimento for rota, capacidade in capacidades.items()
        },
        placar=contadores.placar(),
    )


@app.post("/status/limpar")
def limpar_status():
    """Zera o placar e o histórico do rate limit, para repetir a demonstração."""
    contadores.limpar()
    limite.limpar()
    return jsonify(mensagem="Placar zerado.")


def main() -> None:
    """Sobe o servidor de desenvolvimento do Flask."""
    # Mantém a conexão TCP viva entre requisições. Sem isso, um teste longo no
    # Windows esgota as portas disponíveis e passa a dar erro de conexão.
    from werkzeug.serving import WSGIRequestHandler

    WSGIRequestHandler.protocol_version = "HTTP/1.1"

    print(f"[servidor] http://{config.HOST}:{config.PORTA}")
    app.run(host=config.HOST, port=config.PORTA, threaded=True)


if __name__ == "__main__":
    main()
