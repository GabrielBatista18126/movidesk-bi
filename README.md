# Movidesk BI

Sistema de Business Intelligence para monitoramento de contratos de horas,
produtividade de técnicos e alertas de estouro integrado ao Movidesk.

---

## Índice

1. [Visão geral](#1-visão-geral)
2. [Arquitetura](#2-arquitetura)
3. [Pré-requisitos](#3-pré-requisitos)
4. [Instalação](#4-instalação)
5. [Configuração](#5-configuração)
6. [Subindo o banco de dados](#6-subindo-o-banco-de-dados)
7. [Primeira carga de dados](#7-primeira-carga-de-dados)
8. [Cadastrando os contratos](#8-cadastrando-os-contratos)
9. [Agendando o ETL](#9-agendando-o-etl)
10. [Conectando o Power BI](#10-conectando-o-power-bi)
11. [Dashboards disponíveis](#11-dashboards-disponíveis)
12. [Inteligência e previsões](#12-inteligência-e-previsões)
13. [Alertas por e-mail](#13-alertas-por-e-mail)
14. [Estrutura de arquivos](#14-estrutura-de-arquivos)
15. [Referência de comandos](#15-referência-de-comandos)
16. [Solução de problemas](#16-solução-de-problemas)

---

## 1. Visão geral

O Movidesk BI extrai dados de tickets e lançamentos de horas da API do Movidesk,
armazena em um banco PostgreSQL local e expõe via views e star schema para o Power BI.

**O que o sistema faz:**

- Coleta automaticamente clientes, agentes, tickets e horas lançadas do Movidesk
- Compara o consumo de horas de cada cliente com seu contrato mensal
- Envia alertas por e-mail quando um cliente atinge 80% ou estoura o contrato
- Projeta o consumo até o fim do mês usando taxa diária (alerta preventivo)
- Calcula score de risco por cliente baseado em histórico e tendência
- Sugere upgrades de plano para clientes com padrão de estouro
- Alimenta dashboards no Power BI com dados atualizados 3 vezes ao dia

---

## 2. Arquitetura

```
Movidesk API (OData)
       │
       ▼
  etl/extractor.py      ← coleta paginada com retry e rate limit
       │
       ▼
  etl/transformer.py    ← normaliza e valida os dados
       │
       ▼
  PostgreSQL — schema raw
  ├─ raw.clientes
  ├─ raw.agentes
  ├─ raw.tickets
  ├─ raw.time_entries
  ├─ raw.etl_watermark  (controle incremental)
  └─ raw.etl_log        (histórico de execuções)
       │
       ▼
  etl/dw.py             ← popula star schema
       │
       ▼
  PostgreSQL — schema analytics
  ├─ dim_tempo / dim_clientes / dim_agentes
  ├─ fact_consumo / fact_tickets
  ├─ contratos          (mantido manualmente)
  └─ views analíticas
       │
       ▼
  etl/ml.py             ← previsões e scores
       │
       ├─ previsoes_consumo
       └─ score_clientes
       │
       ▼
  Power BI Desktop / Service
  └─ Dashboards: Consumo | Alertas | Produtividade | Tickets
```

---

## 3. Pré-requisitos

| Software | Versão mínima | Para que serve |
|---|---|---|
| Python | 3.11+ | Rodar o ETL |
| Docker Desktop | qualquer | Rodar o PostgreSQL |
| Power BI Desktop | qualquer | Criar e visualizar dashboards |
| Git | qualquer | Clonar o projeto (opcional) |

> **Sistema operacional:** Windows 10/11 (os scripts de agendamento usam Windows Task Scheduler)

---

## 4. Instalação

### 4.1 Clonar ou copiar o projeto

```bash
# Com Git
git clone <url-do-repositorio> C:\Users\User\movidesk-bi

# Ou simplesmente copiar a pasta para C:\Users\User\movidesk-bi
```

### 4.2 Criar o ambiente virtual Python

Abra o **PowerShell** ou **Prompt de Comando** na pasta do projeto:

```powershell
cd C:\Users\User\movidesk-bi

# Criar ambiente virtual
python -m venv .venv

# Ativar
.venv\Scripts\activate

# Instalar dependências
pip install -r requirements.txt
```

> Se aparecer erro de execução de scripts no PowerShell, rode antes:
> `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

### 4.3 Criar o arquivo de configuração

```powershell
copy .env.example .env
```

Abra o `.env` no editor e preencha as variáveis (veja a seção [5. Configuração](#5-configuração)).

---

## 5. Configuração

Edite o arquivo `.env` na raiz do projeto:

```env
# ── Movidesk ──────────────────────────────────────────────────────
MOVIDESK_TOKEN=SEU_TOKEN_AQUI
MOVIDESK_BASE_URL=https://api.movidesk.com/public/v1

# ── PostgreSQL ────────────────────────────────────────────────────
DB_HOST=localhost
DB_PORT=5432
DB_NAME=movidesk_bi
DB_USER=movidesk_user
DB_PASSWORD=senha_segura_aqui

# ── Alertas por e-mail ────────────────────────────────────────────
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=seu@email.com
SMTP_PASS=senha_de_app          # Gmail: use "Senha de app", não a senha normal
SMTP_FROM=seu@email.com
ALERT_EMAIL=gestor@empresa.com
ALERT_EMAIL_CC=outro@empresa.com,mais@empresa.com   # opcional, separar por vírgula

# ── Thresholds de alerta (%) ──────────────────────────────────────
OVERFLOW_THRESHOLD_WARNING=60   # amarelo: atenção
OVERFLOW_THRESHOLD_CRITICAL=80  # laranja: crítico (dispara e-mail)

# ── ETL ───────────────────────────────────────────────────────────
LOG_LEVEL=INFO
PAGE_SIZE=50
MAX_RETRIES=3
RETRY_DELAY=5
```

### Como obter o token do Movidesk

1. Acesse o Movidesk → **Configurações → Integração → Token de acesso**
2. Gere ou copie o token existente
3. Cole em `MOVIDESK_TOKEN`

### Como configurar o Gmail para alertas

1. Ative a **Verificação em duas etapas** na conta Google
2. Acesse: [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Crie uma "Senha de app" para "Outro (nome personalizado)" → `Movidesk BI`
4. Cole a senha gerada (16 caracteres) em `SMTP_PASS`

---

## 6. Subindo o banco de dados

### 6.1 Iniciar o PostgreSQL via Docker

```powershell
cd C:\Users\User\movidesk-bi
docker-compose up -d
```

O Docker irá:
1. Baixar a imagem `postgres:15-alpine` (apenas na primeira vez)
2. Criar o banco `movidesk_bi`
3. Executar automaticamente todos os scripts SQL da pasta `sql/` em ordem

> Os dados ficam salvos em um volume Docker (`postgres_data`) e persistem
> mesmo após reiniciar o container.

### 6.2 Verificar se subiu corretamente

```powershell
docker ps
```

Deve aparecer o container `movidesk_postgres` com status `healthy`.

```powershell
# Testar conexão
docker exec -it movidesk_postgres psql -U movidesk_user -d movidesk_bi -c "\dn"
```

Deve listar os schemas `raw` e `analytics`.

### 6.3 Parar e reiniciar

```powershell
# Parar (mantém os dados)
docker-compose down

# Reiniciar
docker-compose up -d

# Parar e apagar tudo (CUIDADO: apaga os dados)
docker-compose down -v
```

### 6.4 Configurar inicialização automática com o Windows

Para que o banco suba automaticamente quando o computador ligar:

1. Abra o **Docker Desktop**
2. Vá em **Settings → General**
3. Ative **Start Docker Desktop when you sign in to your computer**

O Docker irá reiniciar os containers com `restart: unless-stopped` automaticamente.

---

## 7. Primeira carga de dados

Com o banco rodando e o `.env` configurado:

```powershell
cd C:\Users\User\movidesk-bi
.venv\Scripts\activate

# Primeira execução: carga completa de todos os dados históricos
python -m etl.main --full
```

O processo faz em sequência:
1. Busca todos os clientes e agentes do Movidesk
2. Busca todos os tickets com horas lançadas
3. Popula o star schema (dimensões + fatos)
4. Calcula previsões e scores de risco
5. Verifica estouros e envia alertas (se configurado)

> A primeira carga pode demorar alguns minutos dependendo do volume de dados.
> O progresso aparece no terminal com timestamps.

### Verificar se os dados foram carregados

```powershell
docker exec -it movidesk_postgres psql -U movidesk_user -d movidesk_bi -c "
SELECT
  (SELECT COUNT(*) FROM raw.clientes)     AS clientes,
  (SELECT COUNT(*) FROM raw.agentes)      AS agentes,
  (SELECT COUNT(*) FROM raw.tickets)      AS tickets,
  (SELECT COUNT(*) FROM raw.time_entries) AS lancamentos;
"
```

---

## 8. Cadastrando os contratos

Os contratos de horas **não vêm do Movidesk** — precisam ser inseridos manualmente.
Sem eles, os dashboards de consumo e alertas não funcionam.

### 8.1 Encontrar o ID do cliente

```sql
-- Conecte ao banco e execute:
SELECT id, business_name, email
FROM raw.clientes
WHERE business_name ILIKE '%nome do cliente%'
ORDER BY business_name;
```

### 8.2 Inserir contratos

```sql
INSERT INTO analytics.contratos
    (client_id, client_name, plano_nome, horas_contratadas, vigencia_inicio)
VALUES
    ('ID_DO_CLIENTE', 'Nome do Cliente S.A.', 'Plano 20h',  20.0, '2025-01-01'),
    ('ID_DO_CLIENTE', 'Outra Empresa Ltda',   'Plano 40h',  40.0, '2025-01-01'),
    ('ID_DO_CLIENTE', 'Empresa Pequena',      'Plano 10h',  10.0, '2025-03-01');
```

### 8.3 Encerrar um contrato (troca de plano)

```sql
-- 1. Encerrar o contrato antigo
UPDATE analytics.contratos
SET vigencia_fim = '2025-12-31'
WHERE client_id = 'ID_DO_CLIENTE' AND vigencia_fim IS NULL;

-- 2. Inserir o novo contrato
INSERT INTO analytics.contratos
    (client_id, client_name, plano_nome, horas_contratadas, vigencia_inicio)
VALUES
    ('ID_DO_CLIENTE', 'Nome do Cliente', 'Plano 60h', 60.0, '2026-01-01');
```

### 8.4 Verificar contratos cadastrados

```sql
SELECT client_name, plano_nome, horas_contratadas, vigencia_inicio, vigencia_fim
FROM analytics.v_contrato_vigente
ORDER BY client_name;
```

---

## 9. Agendando o ETL

O agendamento faz o ETL rodar automaticamente 3x ao dia sem intervenção manual.

### 9.1 Configurar o caminho do Python no script

Abra [scripts/run_etl.bat](scripts/run_etl.bat) e confirme as linhas:

```bat
set PROJECT_DIR=C:\Users\User\movidesk-bi
set PYTHON=%PROJECT_DIR%\.venv\Scripts\python.exe
```

### 9.2 Registrar a tarefa agendada

Abra o **PowerShell como Administrador** e execute:

```powershell
cd C:\Users\User\movidesk-bi
powershell -ExecutionPolicy Bypass -File .\scripts\agendar_etl.ps1
```

Isso registra a tarefa `MovideskBI_ETL` para rodar nos horários **07:00, 12:00 e 18:00**.

### 9.3 Verificar e gerenciar a tarefa

```powershell
# Ver status
Get-ScheduledTask -TaskName "MovideskBI_ETL"

# Rodar agora (teste)
Start-ScheduledTask -TaskName "MovideskBI_ETL"

# Ver logs do dia
type "C:\Users\User\movidesk-bi\scripts\logs\etl_$(Get-Date -Format 'yyyyMMdd').log"

# Remover o agendamento
Unregister-ScheduledTask -TaskName "MovideskBI_ETL" -Confirm:$false
```

---

## 10. Conectando o Power BI

### 10.1 Instalar o driver ODBC do PostgreSQL

1. Baixe o `psqlODBC_x64.msi` em: [postgresql.org/ftp/odbc](https://www.postgresql.org/ftp/odbc/versions/msi/)
2. Instale normalmente

### 10.2 Conectar o Power BI Desktop ao banco

1. Abra o Power BI Desktop
2. **Página Inicial → Obter Dados → PostgreSQL**
3. Preencha:
   - Servidor: `localhost`
   - Banco de dados: `movidesk_bi`
   - Modo: **Importar**
4. Credenciais: usuário e senha conforme o `.env`

### 10.3 Selecionar as views para cada dashboard

No Navegador, expanda o schema `analytics` e selecione:

| View | Dashboard |
|---|---|
| `v_resumo_mes_atual` | KPIs do mês (cards) |
| `v_consumo_mensal` | Histórico de consumo |
| `v_alerta_consumo` | Semáforo de contratos |
| `v_historico_consumo` | Tendência mês a mês |
| `v_produtividade_detalhada` | Horas por agente |
| `v_top_tickets_mes` | Ranking de tickets |
| `v_tickets_abertos` | Tickets em aberto |
| `previsoes_consumo` | Previsão de estouro |
| `score_clientes` | Score de risco |
| `v_sugestoes_upgrade` | Upgrade de plano |
| `v_etl_historico` | Saúde do pipeline |

Para instruções detalhadas de criação dos visuais, consulte [docs/guia_powerbi.md](docs/guia_powerbi.md).

Para configurar refresh automático via Power BI Service, consulte [docs/powerbi_service.md](docs/powerbi_service.md).

---

## 11. Dashboards disponíveis

### Dashboard 1 — Consumo de Contrato
Compara horas consumidas vs. contratadas por cliente no mês selecionado.

**Semáforo:**
- 🟢 **NORMAL** — até 60% consumido
- 🟡 **ATENÇÃO** — 60% a 80%
- 🟠 **CRÍTICO** — 80% a 100% (dispara e-mail)
- 🔴 **ESTOURADO** — acima de 100%

### Dashboard 2 — Alertas
Lista de clientes no limiar de estouro do mês atual, ordenados por % consumo.

### Dashboard 3 — Produtividade
Horas lançadas por técnico, distribuição por cliente e ranking de tickets mais custosos.

### Dashboard 4 — Tickets em Aberto
Todos os tickets ainda ativos com tempo decorrido, urgência e responsável.

### Dashboard 5 — Inteligência
- Previsão de consumo até o fim do mês
- Score de risco 0–100 por cliente
- Sugestões de upgrade de plano

---

## 12. Inteligência e previsões

Executado automaticamente a cada ciclo do ETL, após a carga do star schema.

### Previsão de estouro

Projeta o total de horas que cada cliente consumirá até o fim do mês usando a
**taxa diária atual** (horas consumidas ÷ dias passados × total de dias do mês).

Resultado em `analytics.previsoes_consumo`:

| Campo | Descrição |
|---|---|
| `horas_ate_agora` | Consumo real até hoje |
| `horas_previstas_fim` | Projeção até o último dia do mês |
| `pct_previsto` | % em relação ao contrato |
| `vai_estourar` | `true` se a projeção ultrapassa o contrato |
| `dias_ate_fim_mes` | Dias úteis restantes |

### Score de risco

Pontuação 0–100 calculada com 4 componentes ponderados:

| Componente | Peso | O que mede |
|---|---|---|
| Histórico de estouros | 40% | Meses estourados / total analisado |
| Tendência | 30% | Crescimento do consumo mês a mês (regressão linear) |
| Volatilidade | 20% | Irregularidade do consumo (desvio padrão) |
| Urgência de tickets | 10% | % de tickets High/Urgent no período |

**Classificação:** BAIXO (0–24) | MEDIO (25–49) | ALTO (50–74) | CRITICO (75–100)

### Sugestão de upgrade

A view `analytics.v_sugestoes_upgrade` lista clientes candidatos a upgrade com:
- Média de consumo nos últimos 6 meses
- Horas sugeridas (média × 1,2, arredondado para múltiplo de 5)
- Justificativa: URGENTE / RECOMENDADO / SUGERIDO / OPCIONAL

---

## 13. Alertas por e-mail

O sistema envia e-mails automaticamente em 3 situações:

### Alerta de consumo atual (dispara a cada execução do ETL)
Clientes que atingiram o limiar crítico (padrão: 80%) no mês corrente.
O subject indica se há clientes **ESTOURADOS** (urgente) ou apenas **CRÍTICOS**.

### Alerta preditivo (dispara a cada execução do ETL)
Clientes que ainda não estouraram mas cuja **projeção indica que vão estourar**
antes do fim do mês. Permite ação preventiva.

### Alerta de falha do ETL
Enviado quando o pipeline falha em qualquer etapa, com o traceback do erro.

**Configuração dos destinatários no `.env`:**
```env
ALERT_EMAIL=responsavel@empresa.com
ALERT_EMAIL_CC=gestor@empresa.com,comercial@empresa.com
```

---

## 14. Estrutura de arquivos

```
movidesk-bi/
│
├── .env                        ← configurações (NÃO versionar)
├── .env.example                ← template de configuração
├── docker-compose.yml          ← banco PostgreSQL
├── requirements.txt            ← dependências Python
│
├── etl/                        ← pipeline de dados
│   ├── __init__.py
│   ├── config.py               ← leitura do .env
│   ├── extractor.py            ← coleta da API Movidesk
│   ├── transformer.py          ← normalização dos dados
│   ├── loader.py               ← gravação no PostgreSQL (raw)
│   ├── dw.py                   ← carga do star schema (analytics)
│   ├── ml.py                   ← previsões e scores de risco
│   ├── alerts.py               ← envio de e-mails
│   └── main.py                 ← orquestrador do pipeline
│
├── sql/                        ← scripts de banco (executados em ordem)
│   ├── 01_schemas.sql          ← schemas raw e analytics
│   ├── 02_raw_tables.sql       ← tabelas brutas
│   ├── 03_views.sql            ← views básicas para o Power BI
│   ├── 04_contratos.sql        ← tabela de contratos
│   ├── 05_views_semana34.sql   ← views de alertas e produtividade
│   ├── 06_star_schema.sql      ← dim_* e fact_* para o BI
│   └── 07_inteligencia.sql     ← tabelas de previsões e scores
│
├── scripts/                    ← automação
│   ├── run_etl.bat             ← script chamado pelo agendador
│   ├── agendar_etl.ps1         ← registra tarefa no Task Scheduler
│   └── logs/                   ← logs diários (gerado automaticamente)
│
├── powerbi/
│   └── conexao_powerbi.md      ← guia de conexão Power BI ↔ PostgreSQL
│
└── docs/
    ├── dicionario_dados.md     ← todas as tabelas, colunas e views
    ├── guia_powerbi.md         ← guia de uso dos dashboards para o time
    └── powerbi_service.md      ← refresh automático via Power BI Service
```

---

## 15. Referência de comandos

### ETL

```powershell
# Ativar ambiente virtual
.venv\Scripts\activate

# Carga incremental (padrão — use no dia a dia)
python -m etl.main

# Carga completa (primeira vez ou para reprocessar tudo)
python -m etl.main --full

# Atualizar apenas clientes e agentes (sem tickets)
python -m etl.main --persons
```

### Docker

```powershell
# Subir o banco
docker-compose up -d

# Ver logs do banco
docker-compose logs -f postgres

# Parar o banco (mantém dados)
docker-compose down

# Parar e apagar todos os dados
docker-compose down -v
```

### Banco de dados

```powershell
# Abrir o psql interativo
docker exec -it movidesk_postgres psql -U movidesk_user -d movidesk_bi

# Executar uma query rápida
docker exec -it movidesk_postgres psql -U movidesk_user -d movidesk_bi -c "SELECT * FROM analytics.v_alerta_consumo;"
```

### Agendamento

```powershell
# Registrar agendamento (rodar como Administrador, apenas uma vez)
powershell -ExecutionPolicy Bypass -File .\scripts\agendar_etl.ps1

# Rodar o ETL agora (sem esperar o horário)
Start-ScheduledTask -TaskName "MovideskBI_ETL"

# Ver log do dia atual
type ".\scripts\logs\etl_$(Get-Date -Format 'yyyyMMdd').log"
```

### Queries úteis

```sql
-- Consumo do mês atual por cliente
SELECT * FROM analytics.v_resumo_mes_atual ORDER BY horas_mes_atual DESC;

-- Clientes em alerta (CRÍTICO ou ESTOURADO)
SELECT * FROM analytics.v_alerta_consumo
WHERE status_consumo IN ('CRITICO', 'ESTOURADO')
ORDER BY pct_consumo DESC;

-- Previsões de estouro deste mês
SELECT client_name, horas_ate_agora, horas_previstas_fim, horas_contratadas, pct_previsto
FROM analytics.previsoes_consumo
WHERE mes_referencia = TO_CHAR(CURRENT_DATE, 'YYYY-MM')
ORDER BY pct_previsto DESC;

-- Score de risco dos clientes
SELECT client_name, score_total, classificacao, meses_estourados, tendencia_pct_mes
FROM analytics.score_clientes
ORDER BY score_total DESC;

-- Sugestões de upgrade
SELECT * FROM analytics.v_sugestoes_upgrade;

-- Histórico de execuções do ETL
SELECT * FROM analytics.v_etl_historico LIMIT 10;

-- Últimas watermarks (quando cada tabela foi atualizada)
SELECT * FROM raw.etl_watermark ORDER BY last_run DESC;
```

---

## 16. Solução de problemas

### O ETL falha ao iniciar

**Erro: `KeyError: 'MOVIDESK_TOKEN'`**  
→ O arquivo `.env` não existe ou não foi preenchido.  
→ Execute: `copy .env.example .env` e preencha as variáveis.

**Erro: `could not connect to server`**  
→ O Docker não está rodando.  
→ Execute: `docker-compose up -d` e aguarde o container ficar `healthy`.

**Erro: `ModuleNotFoundError`**  
→ O ambiente virtual não está ativado ou as dependências não foram instaladas.  
→ Execute: `.venv\Scripts\activate` e `pip install -r requirements.txt`.

---

### O banco não sobe

**`docker-compose up -d` não funciona**  
→ Verifique se o Docker Desktop está aberto e rodando.  
→ No Docker Desktop, vá em **Troubleshoot → Reset to factory defaults** se necessário.

**Container sobe mas fica em `starting` ou `unhealthy`**  
→ Verifique se a porta 5432 não está ocupada:

```powershell
netstat -ano | findstr :5432
```

→ Se estiver ocupada, pare o outro PostgreSQL ou mude a porta no `docker-compose.yml`.

---

### O Power BI não conecta ao banco

**"Driver não encontrado"**  
→ Instale o `psqlODBC_x64.msi` (driver 64-bit).

**"Conexão recusada"**  
→ Verifique se o Docker está rodando: `docker ps`.

**"Senha inválida"**  
→ Confirme o usuário e senha no `.env` e no Power BI (eles devem ser iguais).

---

### Os dados estão desatualizados no Power BI

1. Verifique se o ETL rodou recentemente:
```sql
SELECT * FROM analytics.v_etl_historico LIMIT 3;
```

2. Se o ETL está OK, clique em **Atualizar** no Power BI Desktop.

3. Se o agendamento não está rodando, verifique:
```powershell
Get-ScheduledTask -TaskName "MovideskBI_ETL" | Select-Object State, LastRunTime, NextRunTime
```

---

### Alertas por e-mail não chegam

1. Verifique se o SMTP está configurado no `.env`
2. Para Gmail, confirme que está usando uma **Senha de app** (não a senha normal)
3. Teste manualmente:
```powershell
python -c "
from etl.alerts import alert_etl_failure
alert_etl_failure(Exception('Teste de alerta'), step='Manual')
"
```
4. Verifique a pasta de **Spam** do destinatário

---

### Previsões e scores não aparecem

→ Confirme que a tabela `analytics.contratos` está preenchida (sem contratos, não há cálculo).

```sql
SELECT COUNT(*) FROM analytics.contratos;
SELECT COUNT(*) FROM analytics.v_contrato_vigente;
```

→ Se ambas retornarem 0, siga a seção [8. Cadastrando os contratos](#8-cadastrando-os-contratos).
