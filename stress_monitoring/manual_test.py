"""Teste de estresse so com a biblioteca padrao do Python.

Ideia: cada cliente e uma thread que fica consultando notas ate o tempo
acabar. No fim o script mostra quantas respostas de cada tipo chegaram e
quanto elas demoraram.

    python stress_monitoring/manual_test.py
    python stress_monitoring/manual_test.py --rota sem-protecao --clientes 100

"""

from __future__ import annotations

import argparse
import http.client
import json
import random
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

LABELS = {
    "200": "200  boletim entregue",
    "404": "404  inscricao inexistente",
    "429": "429  bloqueado pelo rate limit",
    "503": "503  servidor sobrecarregado",
    "ERRO": "---  sem resposta (timeout / conexao)",
}
WIDTH = 68


# ---------------------------------------------------------------------------
# O cliente
# ---------------------------------------------------------------------------


class Client:
    """Uma pessoa consultando notas: uma thread com sua propria conexao HTTP.

    A conexao e reaproveitada entre as requisicoes. Sem isso, um teste longo
    no Windows acaba com as portas disponiveis e comeca a dar erro de rede
    que nao tem nada a ver com o experimento.
    """

    def __init__(self, number: int, server: urllib.parse.SplitResult) -> None:
        # Identidade propria: sem ela o servidor acharia que todas as threads
        # sao a mesma pessoa, porque todas vem de 127.0.0.1.
        self.client_id = f"manual-{number:03d}"
        self._server = server
        self._connection: http.client.HTTPConnection | None = None

    def request(self, path: str) -> tuple[str, float]:
        """Faz uma requisicao e devolve (status, tempo em segundos)."""
        start_time = time.perf_counter()
        try:
            if self._connection is None:
                self._connection = http.client.HTTPConnection(
                    self._server.hostname,
                    self._server.port or 80,
                    timeout=15,
                )
            self._connection.request(
                "GET", path, headers={"X-Cliente": self.client_id}
            )
            response = self._connection.getresponse()
            response.read()
            status = str(response.status)
        except Exception:
            self.close()  # conexao quebrada: reconecta na proxima tentativa
            status = "ERRO"

        return status, time.perf_counter() - start_time

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None


def run_client(
    number: int,
    route: str,
    registrations: list[str],
    args,
    end_time: float,
) -> list[tuple[str, float]]:
    """Consulta notas sem parar ate o relogio do teste zerar."""
    client = Client(number, args.server_url)
    random_generator = random.Random(number)

    # Os clientes entram aos poucos, igual ao spawn rate do Locust.
    time.sleep(number / args.ramp_rate)

    results = []
    while time.perf_counter() < end_time:
        path = f"/notas/{route}/{random_generator.choice(registrations)}"
        results.append(client.request(path))
        time.sleep(args.pause)

    client.close()
    return results


# ---------------------------------------------------------------------------
# Execucao
# ---------------------------------------------------------------------------


def run_scenario(route: str, registrations: list[str], args) -> dict:
    """Joga todos os clientes em cima de uma rota."""
    ramp_duration = args.clients / args.ramp_rate

    print()
    print("=" * WIDTH)
    print(f"  ROTA  /notas/{route}/<inscricao>")
    print("=" * WIDTH)
    print(
        f"  {args.clients} clientes entrando a {args.ramp_rate:g}/s "
        f"({ramp_duration:.0f}s de rampa)"
    )
    print(
        f"  {args.duration}s de carga | "
        f"{args.pause}s de pausa entre as consultas de cada cliente"
    )
    print("  rodando...", flush=True)

    clear_scoreboard(args.host)
    start_time = time.perf_counter()
    end_time = start_time + ramp_duration + args.duration

    with ThreadPoolExecutor(max_workers=args.clients) as executor:
        futures = [
            executor.submit(run_client, number, route, registrations, args, end_time)
            for number in range(args.clients)
        ]
        results = [item for future in futures for item in future.result()]

    summary = build_summary(route, results, time.perf_counter() - start_time)
    print_summary(summary)
    return summary


def build_summary(route: str, results: list[tuple[str, float]], duration: float) -> dict:
    counts: dict[str, int] = {}
    for status, _ in results:
        counts[status] = counts.get(status, 0) + 1

    return {
        "rota": route,
        "total": len(results),
        "duracao": duration,
        "contagem": counts,
        "tempos": sorted(response_time for _, response_time in results),
    }


def percentile(response_times: list[float], fraction: float) -> float:
    """Percentil simples sobre a lista ja ordenada."""
    if not response_times:
        return 0.0
    return response_times[
        min(int(len(response_times) * fraction), len(response_times) - 1)
    ]


# ---------------------------------------------------------------------------
# Relatorio
# ---------------------------------------------------------------------------


def print_summary(summary: dict) -> None:
    total = summary["total"]
    response_times = summary["tempos"]
    if not total:
        print("  Nenhuma requisicao completada.")
        return

    print()
    print(f"  Requisicoes : {total} em {summary['duracao']:.1f}s "
          f"({total / summary['duracao']:.0f} req/s)")
    print()

    for status in ("200", "404", "429", "503", "ERRO"):
        count = summary["contagem"].get(status)
        if not count:
            continue
        percentage = count / total * 100
        bar = "#" * int(percentage / 2.5)
        print(f"  {LABELS[status]:<38}{count:>6} {percentage:>5.1f}% {bar}")

    print()
    print(
        f"  Tempo de resposta: mediana {percentile(response_times, 0.50) * 1000:.0f} ms | "
        f"p95 {percentile(response_times, 0.95) * 1000:.0f} ms | "
        f"pior {response_times[-1] * 1000:.0f} ms"
    )


def print_comparison(summaries: list[dict]) -> None:
    print()
    print("=" * WIDTH)
    print("  COMPARACAO")
    print("=" * WIDTH)
    print(f"  {'rota':<16}{'200':>8}{'429':>8}{'503':>8}{'perdidas':>12}")
    print("  " + "-" * (WIDTH - 4))

    for summary in summaries:
        counts = summary["contagem"]
        lost_requests = counts.get("503", 0) + counts.get("ERRO", 0)
        percentage = lost_requests / summary["total"] * 100 if summary["total"] else 0
        print(
            f"  {summary['rota']:<16}"
            f"{counts.get('200', 0):>8}"
            f"{counts.get('429', 0):>8}"
            f"{counts.get('503', 0):>8}"
            f"{percentage:>11.1f}%"
        )

    print()
    print("  503 e requisicao PERDIDA: o servidor nao aguentou e derrubou o")
    print("      pedido de alguem que tinha direito a resposta.")
    print("  429 e requisicao RECUSADA de proposito, de graca, antes de gastar")
    print("      recurso - e o servidor segue de pe atendendo todo o resto.")
    print()


def print_error_counts(summaries: list[dict]) -> None:
    """Mostra a quantidade total de falhas observadas em cada rota."""
    print("=" * WIDTH)
    print("  CONTAGEM FINAL DE ERROS")
    print("=" * WIDTH)

    for summary in summaries:
        counts = summary["contagem"]
        errors_503 = counts.get("503", 0)
        connection_errors = counts.get("ERRO", 0)
        total_errors = errors_503 + connection_errors
        print(
            f"  {summary['rota']:<16}{total_errors:>6} erro(s) "
            f"(503: {errors_503}, timeout/conexao: {connection_errors})"
        )

    print()


# ---------------------------------------------------------------------------
# Utilitarios de rede
# ---------------------------------------------------------------------------


def fetch_registrations(host: str) -> list[str]:
    import urllib.request

    with urllib.request.urlopen(f"{host}/alunos", timeout=10) as response:
        return json.loads(response.read())["inscricoes"]


def clear_scoreboard(host: str) -> None:
    import urllib.request

    http_request = urllib.request.Request(
        f"{host}/status/limpar", method="POST", data=b""
    )
    with urllib.request.urlopen(http_request, timeout=10) as response:
        response.read()


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Teste de estresse manual do servidor de notas do ENEM."
    )
    parser.add_argument("--host", default="http://127.0.0.1:5000")
    parser.add_argument(
        "--rota",
        dest="route",
        default="ambas",
        choices=("ambas", "sem-protecao", "com-protecao"),
        help="qual cenario rodar (padrao: os dois, em sequencia)",
    )
    parser.add_argument(
        "--clientes",
        dest="clients",
        type=int,
        default=60,
        help="quantas pessoas simultaneas",
    )
    parser.add_argument(
        "--duracao",
        dest="duration",
        type=int,
        default=20,
        help="segundos de carga cheia",
    )
    parser.add_argument(
        "--pausa",
        type=float,
        default=0.2,
        help="segundos entre as consultas de um mesmo cliente",
        dest="pause",
    )
    parser.add_argument(
        "--rampa",
        type=float,
        default=5.0,
        help="quantos clientes entram por segundo",
        dest="ramp_rate",
    )

    args = parser.parse_args()
    args.host = args.host.rstrip("/")
    args.server_url = urllib.parse.urlsplit(args.host)
    return args


def main() -> None:
    args = parse_arguments()

    try:
        registrations = fetch_registrations(args.host)
    except Exception:
        print(f"Nao consegui falar com {args.host}. O servidor esta rodando?")
        print("Suba ele em outro terminal com:  python -m enem_server")
        return

    routes = (
        ("sem-protecao", "com-protecao")
        if args.route == "ambas"
        else (args.route,)
    )
    summaries = [run_scenario(route, registrations, args) for route in routes]

    if len(summaries) > 1:
        print_comparison(summaries)

    print_error_counts(summaries)


if __name__ == "__main__":
    main()
