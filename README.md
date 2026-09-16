# Teste de Estresse: Rota Protegida vs. Rota Desprotegida

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Flask](https://img.shields.io/badge/Backend-Flask-lightgrey)
![SQLite](https://img.shields.io/badge/Database-SQLite3-green)
![Locust](https://img.shields.io/badge/Testes-Locust-brightgreen)
![Status](https://img.shields.io/badge/Status-Concluído-green)

## 📝 Visão geral

Projeto de apoio ao seminário de **Testes Não Funcionais**, com foco em **Teste de Estresse**. O objetivo é medir, na prática, o que acontece com um serviço quando ele recebe mais requisições do que consegue atender, e qual a diferença concreta que um mecanismo de *rate limit* faz nesse cenário.

O sistema é um servidor de consulta de notas do ENEM, com dados fictícios persistidos em SQLite. Ele expõe duas rotas que executam **exatamente a mesma consulta, com exatamente o mesmo custo**: `GET /notas/sem-protecao/<inscricao>` e `GET /notas/com-protecao/<inscricao>`. A única diferença entre as duas é um `if` no início da segunda, que verifica o limite de requisições do cliente antes de gastar qualquer recurso. Como o trabalho realizado é idêntico, qualquer diferença observada nos resultados pode ser atribuída apenas à proteção.

Para reproduzir uma queda sem sobrecarregar a máquina real, o servidor simula seu próprio limite físico: cada consulta ocupa uma das 15 vagas de atendimento e demora 0,2 segundo. Quando as vagas acabam, a requisição é descartada com **HTTP 503**. Esse 503 representa o servidor caindo, em produção, o usuário veria *timeout* ou conexão recusada, mas o efeito do outro lado é o mesmo: a requisição se perdeu. O rate limit, por sua vez, responde **HTTP 429** sem tocar no banco, o que custa praticamente nada.

A relação entre esses dois números é o que o experimento demonstra:

```
Teto do servidor    = 15 vagas / 0,2s por consulta = 75 requisições por segundo
Gasto por cliente   = 3 consultas / 10 segundos    = 0,3 requisição por segundo
Clientes suportados = 75 / 0,3                     = 250 clientes simultâneos
```

Com rate limit, seriam necessários mais de 250 clientes para ameaçar o servidor. Sem rate limit, bastam 38, porque nada impede um único cliente de fazer 2 requisições por segundo sozinho. Os testes usam 60 clientes: pouco para a rota protegida, muito para a desprotegida.

As duas rotas ficam em `enem_server/app.py`, e os mecanismos comparados (controle de capacidade e rate limit) em `enem_server/limites.py`.

---

## ✨ Principais Funcionalidades

- **Rotas equivalentes para comparação:** duas rotas que consultam o mesmo banco, com o mesmo custo, diferindo apenas pela verificação do rate limit;
- **Rate limit por cliente:** algoritmo de janela deslizante que responde HTTP 429 antes de consumir recurso do servidor, com cabeçalho `Retry-After`;
- **Limite de capacidade simulado:** recusa com HTTP 503 tudo que passa das 15 consultas simultâneas, reproduzindo a queda sem estressar o computador de verdade;
- **Base de dados fictícia:** 100 alunos com notas das cinco áreas do ENEM, gerados automaticamente em SQLite na primeira execução;
- **Teste de estresse em código puro:** script com threads e biblioteca padrão do Python, que imprime a distribuição das respostas e os percentis de tempo;
- **Teste de estresse com ferramenta:** cenário equivalente em Locust, com interface web, gráficos em tempo real e relatório de falhas;
- **Placar do servidor:** rota `/status` com a contagem de requisições atendidas, bloqueadas e perdidas em cada cenário;
- **Parâmetros centralizados:** todos os números do experimento reunidos em um único arquivo de configuração.

---

## 🛠 Tecnologias Utilizadas

Este projeto foi desenvolvido utilizando as seguintes tecnologias:

- **Linguagem Principal:** [Python](https://www.python.org/);
- **Servidor / API REST:** [Flask](https://flask.palletsprojects.com/);
- **Banco de Dados:** SQLite3 (nativo do Python);
- **Teste de carga por ferramenta:** [Locust](https://locust.io/);
- **Teste de carga por código:** `threading`, `http.client` e `concurrent.futures` (biblioteca padrão).

---

## 🚀 Passos para execução

### Pré-requisitos

  Antes de começar, certifique-se de ter instalado em sua máquina:

- [Python 3.10+](https://www.python.org/downloads/);
- [Git](https://git-scm.com/).

### Passo 1. Clone o repositório

```bash
    git clone <url-do-repositorio>
```

### Passo 2. Configuração do Ambiente Virtual

  Crie e ative o ambiente virtual para isolar as dependências do projeto:

  **Linux / macOS:**

```bash
    python -m venv .venv
    source .venv/bin/activate
```

  **Windows:**

```bash
    python -m venv .venv
    .venv/Scripts/activate
```

### Passo 3. Instalação das Dependências

  Com o ambiente virtual ativo, instale as bibliotecas necessárias:

```bash
    pip install -r requirements.txt
```

### Passo 4. Iniciando o Servidor

  Na raiz do projeto, execute:

```bash
    python -m enem_server
```

  Na primeira execução o banco `enem.db` é criado e populado automaticamente com os 100 alunos. O servidor fica disponível em http://127.0.0.1:5000.

  OBS.: Deixe este terminal aberto. Todos os passos seguintes exigem o servidor rodando.

  Para confirmar que está tudo no ar, consulte um aluno:

```bash
    curl.exe http://127.0.0.1:5000/notas/sem-protecao/240000000001
```

```json
  {
    "inscricao": "240000000001",
    "nome": "Diego Almeida",
    "uf": "MG",
    "notas": { "linguagens": 521.6, "humanas": 569.3, "natureza": 638.2,
               "matematica": 608.8, "redacao": 680.0 },
    "media": 603.6
  }
```

  Repetindo o comando abaixo quatro vezes seguidas, o rate limit age na quarta:

```bash
    curl.exe http://127.0.0.1:5000/notas/com-protecao/240000000001
```

```json
  {
    "erro": "muitas_requisicoes",
    "mensagem": "Você já fez 3 consultas nos últimos 10 segundos. Tente de novo em 8 segundos.",
    "tentar_em_segundos": 8
  }
```

  OBS.: No PowerShell, use `curl.exe` com a extensão. O `curl` sozinho é apelido de `Invoke-WebRequest`, que trata 429 e 503 como exceção. Abrir a URL no navegador também funciona.

### Passo 5. Teste de Estresse em Código Puro

  Abra um novo terminal, ative o ambiente virtual e execute o script. Ele roda os dois cenários em sequência e imprime a comparação no final:

```bash
    python stress_monitoring/teste_manual.py
```

  A execução leva cerca de um minuto. Os parâmetros podem ser ajustados:

| Argumento      | Padrão   | O que é                                        |
| -------------- | --------- | ----------------------------------------------- |
| `--rota`     | `ambas` | `sem-protecao`, `com-protecao` ou `ambas` |
| `--clientes` | `60`    | quantas pessoas simultâneas                    |
| `--duracao`  | `20`    | segundos de carga cheia, após a rampa          |
| `--pausa`    | `0.2`   | segundos entre as consultas de um mesmo cliente |
| `--rampa`    | `5`     | quantos clientes entram por segundo             |

```bash
    python stress_monitoring/teste_manual.py --rota sem-protecao --clientes 100 --duracao 30
```

### Passo 6. Teste de Estresse com Locust

  O mesmo cenário, mas com a ferramenta cuidando das threads, das métricas e dos gráficos. Cada rota é isolada por uma *tag*:

```bash
    locust -f stress_monitoring/locustfile.py --host http://127.0.0.1:5000 --tags sem-protecao
```

  Abra http://localhost:8089, informe **60 users** e **spawn rate 5**, inicie o teste e acompanhe a aba *Charts*. Depois repita trocando a tag para `com-protecao`.

  Para rodar sem interface, com os parâmetros já definidos:

```bash
    locust -f stress_monitoring/locustfile.py --host http://127.0.0.1:5000 --tags sem-protecao --users 60 --spawn-rate 5 --run-time 30s --headless
    locust -f stress_monitoring/locustfile.py --host http://127.0.0.1:5000 --tags com-protecao --users 60 --spawn-rate 5 --run-time 30s --headless
```

---

## 📊 Resultados obtidos

Ambos os testes foram executados com 60 clientes simultâneos contra cada rota.

**Teste em código puro** (60 clientes, 20 segundos de carga):

| Rota             | Atendidas (200) | Bloqueadas (429) | Perdidas (503) | % perdida       |
| ---------------- | --------------- | ---------------- | -------------- | --------------- |
| `sem-protecao` | 2.042           | 0                | 2.969          | **59,2%** |
| `com-protecao` | 547             | 4.969            | 0              | **0,0%**  |

**Teste com Locust** (60 users, spawn rate 5, 30 segundos):

| Rota             | Requisições | Falhas                                | p95    |
| ---------------- | ------------- | ------------------------------------- | ------ |
| `sem-protecao` | 2.510         | **992 (39,5%)**, todas HTTP 503 | 480 ms |
| `com-protecao` | 3.779         | **0 (0%)**                      | 240 ms |

Dois pontos merecem atenção na leitura desses números:

- **O 429 não é contabilizado como falha no Locust.** Ele não é um erro, e sim o servidor funcionando corretamente e avisando o cliente para desacelerar. Já o 503 é uma resposta que o usuário deveria ter recebido e perdeu. A contagem de bloqueios fica visível em `/status`;
- **A rota protegida entregou menos boletins** (547 contra 2.042). O rate limit está calibrado de forma conservadora: 60 clientes gastam apenas 18 req/s de um teto de 75, sobrando capacidade em troca de estabilidade. A rota sem proteção entregou mais, mas descartou 2.969 pedidos no caminho.

---

## ⚙️ Ajustando o experimento

Todos os números ficam em `enem_server/config.py`. Reinicie o servidor após editar.

| Constante                      | Padrão | Efeito                                                                |
| ------------------------------ | ------- | --------------------------------------------------------------------- |
| `CAPACIDADE_SIMULTANEA`      | `15`  | quantas consultas cabem ao mesmo tempo; quanto menor, mais fácil cai |
| `TEMPO_DA_CONSULTA_SEGUNDOS` | `0.2` | quanto cada consulta demora                                           |
| `LIMITE_DE_REQUISICOES`      | `3`   | quantas consultas cada cliente pode fazer...                          |
| `JANELA_EM_SEGUNDOS`         | `10`  | ...dentro desse intervalo                                             |

Aumentar `LIMITE_DE_REQUISICOES` para `12` faz o servidor entregar muito mais boletins sem cair, o que ilustra o ajuste fino da proteção. Em `30`, ele volta a cair.

Se a rota sem proteção não estiver caindo na sua máquina, aumente `--clientes` ou reduza `CAPACIDADE_SIMULTANEA`. Se a rota protegida estiver devolvendo 503, reduza `--rampa` para que os clientes entrem de forma mais suave.
