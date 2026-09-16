"""Teste de estresse so com a biblioteca padrao do Python.

Ideia: cada cliente e uma thread que fica consultando notas ate o tempo
acabar. No fim o script mostra quantas respostas de cada tipo chegaram e
quanto elas demoraram.

    python stress_monitoring/teste_manual.py
    python stress_monitoring/teste_manual.py --rota sem-protecao --clientes 100

    
"""

from __future__ import annotations

import argparse
import http.client
import json
import random
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

ROTULOS = {
    "200": "200  boletim entregue",
    "404": "404  inscricao inexistente",
    "429": "429  bloqueado pelo rate limit",
    "503": "503  servidor sobrecarregado",
    "ERRO": "---  sem resposta (timeout / conexao)",
}
LARGURA = 68


# ---------------------------------------------------------------------------
# O cliente
# ---------------------------------------------------------------------------


class Cliente:
    """Uma pessoa consultando notas: uma thread com sua propria conexao HTTP.

    A conexao e reaproveitada entre as requisicoes. Sem isso, um teste longo
    no Windows acaba com as portas disponiveis e comeca a dar erro de rede
    que nao tem nada a ver com o experimento.
    """

    def __init__(self, numero: int, servidor: urllib.parse.SplitResult) -> None:
        # Identidade propria: sem ela o servidor acharia que todas as threads
        # sao a mesma pessoa, porque todas vem de 127.0.0.1.
        self.identificacao = f"manual-{numero:03d}"
        self._servidor = servidor
        self._conexao: http.client.HTTPConnection | None = None

    def requisitar(self, caminho: str) -> tuple[str, float]:
        """Faz uma requisicao e devolve (status, tempo em segundos)."""
        inicio = time.perf_counter()
        try:
            if self._conexao is None:
                self._conexao = http.client.HTTPConnection(
                    self._servidor.hostname,
                    self._servidor.port or 80,
                    timeout=15,
                )
            self._conexao.request(
                "GET", caminho, headers={"X-Cliente": self.identificacao}
            )
            resposta = self._conexao.getresponse()
            resposta.read()
            status = str(resposta.status)
        except Exception:
            self.fechar()  # conexao quebrada: reconecta na proxima tentativa
            status = "ERRO"

        return status, time.perf_counter() - inicio

    def fechar(self) -> None:
        if self._conexao is not None:
            self._conexao.close()
            self._conexao = None


def rodar_cliente(
    numero: int,
    rota: str,
    inscricoes: list[str],
    argumentos,
    fim: float,
) -> list[tuple[str, float]]:
    """Consulta notas sem parar ate o relogio do teste zerar."""
    cliente = Cliente(numero, argumentos.servidor)
    sorteio = random.Random(numero)

    # Os clientes entram aos poucos, igual ao spawn rate do Locust.
    time.sleep(numero / argumentos.rampa)

    resultados = []
    while time.perf_counter() < fim:
        caminho = f"/notas/{rota}/{sorteio.choice(inscricoes)}"
        resultados.append(cliente.requisitar(caminho))
        time.sleep(argumentos.pausa)

    cliente.fechar()
    return resultados


# ---------------------------------------------------------------------------
# Execucao
# ---------------------------------------------------------------------------


def executar_cenario(rota: str, inscricoes: list[str], argumentos) -> dict:
    """Joga todos os clientes em cima de uma rota."""
    tempo_de_rampa = argumentos.clientes / argumentos.rampa

    print()
    print("=" * LARGURA)
    print(f"  ROTA  /notas/{rota}/<inscricao>")
    print("=" * LARGURA)
    print(
        f"  {argumentos.clientes} clientes entrando a {argumentos.rampa:g}/s "
        f"({tempo_de_rampa:.0f}s de rampa)"
    )
    print(
        f"  {argumentos.duracao}s de carga | "
        f"{argumentos.pausa}s de pausa entre as consultas de cada cliente"
    )
    print("  rodando...", flush=True)

    zerar_placar(argumentos.host)
    comeco = time.perf_counter()
    fim = comeco + tempo_de_rampa + argumentos.duracao

    with ThreadPoolExecutor(max_workers=argumentos.clientes) as executor:
        tarefas = [
            executor.submit(rodar_cliente, numero, rota, inscricoes, argumentos, fim)
            for numero in range(argumentos.clientes)
        ]
        resultados = [item for tarefa in tarefas for item in tarefa.result()]

    resumo = montar_resumo(rota, resultados, time.perf_counter() - comeco)
    imprimir_resumo(resumo)
    return resumo


def montar_resumo(rota: str, resultados: list[tuple[str, float]], duracao: float) -> dict:
    contagem: dict[str, int] = {}
    for status, _ in resultados:
        contagem[status] = contagem.get(status, 0) + 1

    return {
        "rota": rota,
        "total": len(resultados),
        "duracao": duracao,
        "contagem": contagem,
        "tempos": sorted(tempo for _, tempo in resultados),
    }


def percentil(tempos: list[float], fracao: float) -> float:
    """Percentil simples sobre a lista ja ordenada."""
    if not tempos:
        return 0.0
    return tempos[min(int(len(tempos) * fracao), len(tempos) - 1)]


# ---------------------------------------------------------------------------
# Relatorio
# ---------------------------------------------------------------------------


def imprimir_resumo(resumo: dict) -> None:
    total = resumo["total"]
    tempos = resumo["tempos"]
    if not total:
        print("  Nenhuma requisicao completada.")
        return

    print()
    print(f"  Requisicoes : {total} em {resumo['duracao']:.1f}s "
          f"({total / resumo['duracao']:.0f} req/s)")
    print()

    for status in ("200", "404", "429", "503", "ERRO"):
        quantidade = resumo["contagem"].get(status)
        if not quantidade:
            continue
        fatia = quantidade / total * 100
        barra = "#" * int(fatia / 2.5)
        print(f"  {ROTULOS[status]:<38}{quantidade:>6} {fatia:>5.1f}% {barra}")

    print()
    print(
        f"  Tempo de resposta: mediana {percentil(tempos, 0.50) * 1000:.0f} ms | "
        f"p95 {percentil(tempos, 0.95) * 1000:.0f} ms | "
        f"pior {tempos[-1] * 1000:.0f} ms"
    )


def imprimir_comparacao(resumos: list[dict]) -> None:
    print()
    print("=" * LARGURA)
    print("  COMPARACAO")
    print("=" * LARGURA)
    print(f"  {'rota':<16}{'200':>8}{'429':>8}{'503':>8}{'perdidas':>12}")
    print("  " + "-" * (LARGURA - 4))

    for resumo in resumos:
        contagem = resumo["contagem"]
        perdidas = contagem.get("503", 0) + contagem.get("ERRO", 0)
        fatia = perdidas / resumo["total"] * 100 if resumo["total"] else 0
        print(
            f"  {resumo['rota']:<16}"
            f"{contagem.get('200', 0):>8}"
            f"{contagem.get('429', 0):>8}"
            f"{contagem.get('503', 0):>8}"
            f"{fatia:>11.1f}%"
        )

    print()
    print("  503 e requisicao PERDIDA: o servidor nao aguentou e derrubou o")
    print("      pedido de alguem que tinha direito a resposta.")
    print("  429 e requisicao RECUSADA de proposito, de graca, antes de gastar")
    print("      recurso - e o servidor segue de pe atendendo todo o resto.")
    print()


def imprimir_contagem_erros(resumos: list[dict]) -> None:
    """Mostra a quantidade total de falhas observadas em cada rota."""
    print("=" * LARGURA)
    print("  CONTAGEM FINAL DE ERROS")
    print("=" * LARGURA)

    for resumo in resumos:
        contagem = resumo["contagem"]
        erros_503 = contagem.get("503", 0)
        erros_conexao = contagem.get("ERRO", 0)
        total_erros = erros_503 + erros_conexao
        print(
            f"  {resumo['rota']:<16}{total_erros:>6} erro(s) "
            f"(503: {erros_503}, timeout/conexao: {erros_conexao})"
        )

    print()


# ---------------------------------------------------------------------------
# Utilitarios de rede
# ---------------------------------------------------------------------------


def buscar_inscricoes(host: str) -> list[str]:
    import urllib.request

    with urllib.request.urlopen(f"{host}/alunos", timeout=10) as resposta:
        return json.loads(resposta.read())["inscricoes"]


def zerar_placar(host: str) -> None:
    import urllib.request

    pedido = urllib.request.Request(f"{host}/status/limpar", method="POST", data=b"")
    with urllib.request.urlopen(pedido, timeout=10) as resposta:
        resposta.read()


def ler_argumentos():
    analisador = argparse.ArgumentParser(
        description="Teste de estresse manual do servidor de notas do ENEM."
    )
    analisador.add_argument("--host", default="http://127.0.0.1:5000")
    analisador.add_argument(
        "--rota",
        default="ambas",
        choices=("ambas", "sem-protecao", "com-protecao"),
        help="qual cenario rodar (padrao: os dois, em sequencia)",
    )
    analisador.add_argument(
        "--clientes", type=int, default=60, help="quantas pessoas simultaneas"
    )
    analisador.add_argument(
        "--duracao", type=int, default=20, help="segundos de carga cheia"
    )
    analisador.add_argument(
        "--pausa",
        type=float,
        default=0.2,
        help="segundos entre as consultas de um mesmo cliente",
    )
    analisador.add_argument(
        "--rampa", type=float, default=5.0, help="quantos clientes entram por segundo"
    )

    argumentos = analisador.parse_args()
    argumentos.host = argumentos.host.rstrip("/")
    argumentos.servidor = urllib.parse.urlsplit(argumentos.host)
    return argumentos


def main() -> None:
    argumentos = ler_argumentos()

    try:
        inscricoes = buscar_inscricoes(argumentos.host)
    except Exception:
        print(f"Nao consegui falar com {argumentos.host}. O servidor esta rodando?")
        print("Suba ele em outro terminal com:  python -m enem_server")
        return

    rotas = (
        ("sem-protecao", "com-protecao")
        if argumentos.rota == "ambas"
        else (argumentos.rota,)
    )
    resumos = [executar_cenario(rota, inscricoes, argumentos) for rota in rotas]

    if len(resumos) > 1:
        imprimir_comparacao(resumos)

    imprimir_contagem_erros(resumos)


if __name__ == "__main__":
    main()
