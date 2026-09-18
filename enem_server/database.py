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

_FIRST_NAMES = (
    "Ana", "Bruno", "Carla", "Diego", "Elisa", "Felipe", "Gabriela", "Heitor",
    "Isabela", "João", "Karina", "Lucas", "Mariana", "Nícolas", "Olívia",
    "Pedro", "Rafaela", "Samuel", "Tainá", "Vitor",
)
_LAST_NAMES = (
    "Almeida", "Barbosa", "Cardoso", "Duarte", "Esteves", "Fernandes",
    "Gonçalves", "Henriques", "Lima", "Moraes", "Nogueira", "Oliveira",
    "Pereira", "Queiroz", "Ribeiro", "Santos", "Teixeira", "Vieira",
)
_STATES = ("SC", "PR", "RS", "SP", "MG", "BA", "PE", "CE", "GO", "AM")

_CREATE_TABLE_SQL = """
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


def _connect() -> sqlite3.Connection:
    """Abre uma conexão nova. SQLite aceita vários leitores ao mesmo tempo,
    então cada requisição pode abrir a sua sem disputar trava."""
    connection = sqlite3.connect(config.DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def _generate_students() -> list[tuple]:
    """Inventa os alunos. O `Random(42)` garante que o banco sai igual
    em qualquer computador, o que facilita repetir a demonstração."""
    random_generator = random.Random(42)
    students = []

    for position in range(config.TOTAL_STUDENTS):
        registration_id = str(config.FIRST_REGISTRATION + position)
        name = f"{random_generator.choice(_FIRST_NAMES)} {random_generator.choice(_LAST_NAMES)}"
        state = random_generator.choice(_STATES)

        # Notas objetivas giram em torno de 520, como no ENEM real.
        objective_scores = [
            round(min(900.0, max(300.0, random_generator.gauss(520, 90))), 1)
            for _ in range(4)
        ]
        essay_score = float(random_generator.randrange(0, 1001, 20))

        students.append((registration_id, name, state, *objective_scores, essay_score))

    return students


def initialize_database_if_needed() -> None:
    """Cria a tabela e popula o banco na primeira execução."""
    with closing(_connect()) as connection:
        connection.execute(_CREATE_TABLE_SQL)
        (count,) = connection.execute("SELECT COUNT(*) FROM alunos").fetchone()

        if count == 0:
            connection.executemany(
                "INSERT INTO alunos VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                _generate_students(),
            )
            connection.commit()
            print(
                f"[banco] {config.TOTAL_STUDENTS} alunos ficticios criados em "
                f"{config.DATABASE_PATH}"
            )
        else:
            print(f"[banco] {count} alunos carregados de {config.DATABASE_PATH}")


def get_student(registration_id: str) -> dict | None:
    """Devolve o boletim de um aluno, ou None se a inscrição não existir."""
    with closing(_connect()) as connection:
        row = connection.execute(
            "SELECT * FROM alunos WHERE inscricao = ?", (registration_id,)
        ).fetchone()

    if row is None:
        return None

    scores = {area: row[area] for area in AREAS}
    return {
        "inscricao": row["inscricao"],
        "nome": row["nome"],
        "uf": row["uf"],
        "notas": scores,
        "media": round(sum(scores.values()) / len(scores), 1),
    }


def list_registrations() -> list[str]:
    """Todas as inscrições cadastradas. Os testes usam isso para sortear
    qual aluno consultar."""
    with closing(_connect()) as connection:
        rows = connection.execute("SELECT inscricao FROM alunos ORDER BY inscricao")
        return [row["inscricao"] for row in rows]
