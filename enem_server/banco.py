"""Banco SQLite com notas fictícias do ENEM.

O arquivo `enem.db` é criado e populado sozinho na primeira execução do
servidor. Nenhum dado aqui é real.
"""

from __future__ import annotations

import random
import sqlite3
from contextlib import closing

from . import config

AREAS = ("linguagens", "humanas", "natureza", "matematica", "redacao")

_NOMES = (
    "Ana", "Bruno", "Carla", "Diego", "Elisa", "Felipe", "Gabriela", "Heitor",
    "Isabela", "João", "Karina", "Lucas", "Mariana", "Nícolas", "Olívia",
    "Pedro", "Rafaela", "Samuel", "Tainá", "Vitor",
)
_SOBRENOMES = (
    "Almeida", "Barbosa", "Cardoso", "Duarte", "Esteves", "Fernandes",
    "Gonçalves", "Henriques", "Lima", "Moraes", "Nogueira", "Oliveira",
    "Pereira", "Queiroz", "Ribeiro", "Santos", "Teixeira", "Vieira",
)
_UFS = ("SC", "PR", "RS", "SP", "MG", "BA", "PE", "CE", "GO", "AM")

_SQL_CRIAR_TABELA = """
CREATE TABLE IF NOT EXISTS alunos (
    inscricao   TEXT PRIMARY KEY,
    nome        TEXT NOT NULL,
    uf          TEXT NOT NULL,
    linguagens  REAL NOT NULL,
    humanas     REAL NOT NULL,
    natureza    REAL NOT NULL,
    matematica  REAL NOT NULL,
    redacao     REAL NOT NULL
)
"""


def _conectar() -> sqlite3.Connection:
    """Abre uma conexão nova. SQLite aceita vários leitores ao mesmo tempo,
    então cada requisição pode abrir a sua sem disputar trava."""
    conexao = sqlite3.connect(config.CAMINHO_BANCO)
    conexao.row_factory = sqlite3.Row
    return conexao


def _gerar_alunos() -> list[tuple]:
    """Inventa os alunos. O `Random(42)` garante que o banco sai igual
    em qualquer computador, o que facilita repetir a demonstração."""
    sorteio = random.Random(42)
    alunos = []

    for posicao in range(config.TOTAL_DE_ALUNOS):
        inscricao = str(config.PRIMEIRA_INSCRICAO + posicao)
        nome = f"{sorteio.choice(_NOMES)} {sorteio.choice(_SOBRENOMES)}"
        uf = sorteio.choice(_UFS)

        # Notas objetivas giram em torno de 520, como no ENEM real.
        objetivas = [
            round(min(900.0, max(300.0, sorteio.gauss(520, 90))), 1)
            for _ in range(4)
        ]
        redacao = float(sorteio.randrange(0, 1001, 20))

        alunos.append((inscricao, nome, uf, *objetivas, redacao))

    return alunos


def criar_banco_se_necessario() -> None:
    """Cria a tabela e popula o banco na primeira execução."""
    with closing(_conectar()) as conexao:
        conexao.execute(_SQL_CRIAR_TABELA)
        (quantidade,) = conexao.execute("SELECT COUNT(*) FROM alunos").fetchone()

        if quantidade == 0:
            conexao.executemany(
                "INSERT INTO alunos VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                _gerar_alunos(),
            )
            conexao.commit()
            print(
                f"[banco] {config.TOTAL_DE_ALUNOS} alunos ficticios criados em "
                f"{config.CAMINHO_BANCO}"
            )
        else:
            print(f"[banco] {quantidade} alunos carregados de {config.CAMINHO_BANCO}")


def buscar_aluno(inscricao: str) -> dict | None:
    """Devolve o boletim de um aluno, ou None se a inscrição não existir."""
    with closing(_conectar()) as conexao:
        linha = conexao.execute(
            "SELECT * FROM alunos WHERE inscricao = ?", (inscricao,)
        ).fetchone()

    if linha is None:
        return None

    notas = {area: linha[area] for area in AREAS}
    return {
        "inscricao": linha["inscricao"],
        "nome": linha["nome"],
        "uf": linha["uf"],
        "notas": notas,
        "media": round(sum(notas.values()) / len(notas), 1),
    }


def listar_inscricoes() -> list[str]:
    """Todas as inscrições cadastradas. Os testes usam isso para sortear
    qual aluno consultar."""
    with closing(_conectar()) as conexao:
        linhas = conexao.execute("SELECT inscricao FROM alunos ORDER BY inscricao")
        return [linha["inscricao"] for linha in linhas]
