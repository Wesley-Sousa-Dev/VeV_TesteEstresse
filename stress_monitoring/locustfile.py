"""Teste de estresse com ferramenta (Locust).

Mesmo cenário do `teste_manual.py`, mas quem cuida das threads, das métricas
e dos gráficos é o Locust.

    locust -f stress_monitoring/locustfile.py --host http://127.0.0.1:5000
"""

import random
import uuid

from locust import HttpUser, between, tag, task


class AlunoConsultandoNotas(HttpUser):
    """Uma pessoa apertando F5 na página de notas."""

    # Tempo de espera entre uma consulta e a próxima.
    wait_time = between(0.1, 0.5)

    def on_start(self) -> None:
        """Roda uma vez quando o usuário virtual nasce."""
        # Identidade própria para o rate limit. Sem isso o servidor veria
        # todos os usuários do Locust como um único cliente (127.0.0.1).
        self.client.headers["X-Cliente"] = f"locust-{uuid.uuid4().hex[:8]}"

        resposta = self.client.get("/alunos", name="GET /alunos (preparacao)")
        self.inscricoes = resposta.json()["inscricoes"]

    @tag("sem-protecao")
    @task
    def consultar_sem_protecao(self) -> None:
        """A rota que cai: qualquer coisa diferente de 200 é falha."""
        with self.client.get(
            f"/notas/sem-protecao/{random.choice(self.inscricoes)}",
            name="GET /notas/sem-protecao",
            catch_response=True,
        ) as resposta:
            if resposta.status_code == 200:
                resposta.success()
            else:
                resposta.failure(f"HTTP {resposta.status_code}")

    @tag("com-protecao")
    @task
    def consultar_com_protecao(self) -> None:
        """A rota protegida.

        O 429 é contado como SUCESSO de propósito: ele é a resposta correta
        do servidor para excesso de chamadas, não uma falha. Quem quiser ver
        quantos foram bloqueados abre GET /status. Assim o painel do Locust
        mostra exatamente o que o seminário quer provar: esta rota termina o
        teste com 0% de falhas.
        """
        with self.client.get(
            f"/notas/com-protecao/{random.choice(self.inscricoes)}",
            name="GET /notas/com-protecao",
            catch_response=True,
        ) as resposta:
            if resposta.status_code in (200, 429):
                resposta.success()
            else:
                resposta.failure(f"HTTP {resposta.status_code}")
