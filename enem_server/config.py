from pathlib import Path

# ---------------------------------------------------------------------------
# Banco de dados (dados fictícios de alunos do ENEM)
# ---------------------------------------------------------------------------
DATABASE_PATH = Path(__file__).resolve().parent.parent / "enem.db"
TOTAL_STUDENTS = 100
FIRST_REGISTRATION = 240000000001

# ---------------------------------------------------------------------------
# O "limite falso" do servidor
# ---------------------------------------------------------------------------
# Quantas consultas o servidor consegue processar ao mesmo tempo.
# Passou disso, ele responde 503 em vez de travar o computador de verdade.
CONCURRENT_CAPACITY = 15

# Quanto tempo cada consulta demora (simula um banco de produção lento).
QUERY_DURATION_SECONDS = 0.2

# ---------------------------------------------------------------------------
# O rate limit (a proteção que está sendo avaliada)
# ---------------------------------------------------------------------------
# Cada cliente pode fazer REQUEST_LIMIT a cada WINDOW_SECONDS.
REQUEST_LIMIT = 3
WINDOW_SECONDS = 10

# ---------------------------------------------------------------------------
# A CONTA QUE EXPLICA O EXPERIMENTO INTEIRO
# ---------------------------------------------------------------------------
# Teto do servidor   = CONCURRENT_CAPACITY / QUERY_DURATION_SECONDS
#                    = 15 / 0,2 = 75 requisições por segundo
#
# Gasto por cliente  = REQUEST_LIMIT / WINDOW_SECONDS
#                    = 3 / 10  = 0,3 requisição por segundo
#
# Clientes que cabem = 75 / 0,3 = 250 clientes simultâneos
#
# Ou seja: COM rate limit seriam necessários mais de 250 clientes para chegar
# perto do teto. SEM rate limit bastam ~38, porque nada impede um único
# cliente de fazer 2 requisições por segundo sozinho.
#
# Os testes usam 60 clientes: é pouco para a rota protegida (60 x 0,3 = 18
# req/s, 24% do teto) e demais para a rota desprotegida (60 x 2 = 120 req/s,
# 160% do teto).
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Servidor HTTP
# ---------------------------------------------------------------------------
HOST = "127.0.0.1"
PORT = 5000
